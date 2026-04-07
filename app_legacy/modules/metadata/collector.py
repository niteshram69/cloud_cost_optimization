"""Metadata extraction and collection logic."""

import csv
import hashlib
import json
from datetime import datetime
from typing import Any

import magic

from app.core.constants import CloudProvider


class MetadataCollector:
    """Extracts metadata from various data formats (CSV, JSON, billing exports)."""
    
    # Field mappings for common billing formats
    AWS_BILLING_FIELDS = {
        'line_item_resource_id': 'resource_id',
        'line_item_usage_account_id': 'account_id',
        'bill_payer_account_id': 'payer_account_id',
        'line_item_usage_type': 'usage_type',
        'line_item_operation': 'operation',
        'line_item_availability_zone': 'availability_zone',
        'product_region_code': 'region',
        'line_item_product_code': 'service_type',
        'line_item_usage_amount': 'usage_quantity',
        'line_item_usage_start_date': 'usage_start',
        'line_item_usage_end_date': 'usage_end',
        'line_item_blended_cost': 'cost_amount',
        'line_item_currency_code': 'currency',
        'resource_tags': 'tags',
    }
    
    GCP_BILLING_FIELDS = {
        'resource.name': 'resource_id',
        'project.id': 'account_id',
        'service.description': 'service_type',
        'sku.description': 'sku_description',
        'usage_start_time': 'usage_start',
        'usage_end_time': 'usage_end',
        'cost': 'cost_amount',
        'currency': 'currency',
        'labels': 'tags',
        'location.location': 'region',
    }
    
    AZURE_BILLING_FIELDS = {
        'ResourceId': 'resource_id',
        'SubscriptionId': 'account_id',
        'ResourceGroup': 'resource_group',
        'MeterCategory': 'service_type',
        'MeterSubCategory': 'service_subtype',
        'UsageStartTime': 'usage_start',
        'UsageEndTime': 'usage_end',
        'Cost': 'cost_amount',
        'Currency': 'currency',
        'Tags': 'tags',
        'ResourceLocation': 'region',
    }
    
    def detect_file_format(self, file_path: str, mime_type: str) -> str:
        """Detect the format of the input file."""
        mime_mapping = {
            'text/csv': 'csv',
            'application/json': 'json',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            'application/vnd.ms-excel': 'xls',
            'application/gzip': 'gz',
            'application/zip': 'zip',
            'text/plain': 'txt',
        }
        
        detected = mime_mapping.get(mime_type)
        if detected:
            return detected
        
        # Fallback: check file extension
        if file_path.endswith('.csv'):
            return 'csv'
        elif file_path.endswith('.json'):
            return 'json'
        elif file_path.endswith(('.xlsx', '.xls')):
            return 'xlsx'
        elif file_path.endswith('.gz'):
            return 'gz'
        elif file_path.endswith('.zip'):
            return 'zip'
        
        return 'unknown'
    
    def detect_provider(self, headers: list[str], sample_data: dict) -> str:
        """Detect cloud provider from data headers and sample."""
        header_set = set(h.lower() for h in headers)
        
        # Check for AWS patterns
        aws_patterns = ['line_item_resource_id', 'bill_payer_account_id', 'line_item_product_code']
        if any(p in header_set for p in aws_patterns):
            return CloudProvider.AWS.value
        
        # Check for GCP patterns
        gcp_patterns = ['project.id', 'service.description', 'sku.description']
        if any(p.lower().replace('.', '_') in header_set for p in gcp_patterns):
            return CloudProvider.GCP.value
        
        # Check for Azure patterns
        azure_patterns = ['resourceid', 'subscriptionid', 'metercategory']
        if any(p in header_set for p in azure_patterns):
            return CloudProvider.AZURE.value
        
        return CloudProvider.OTHER.value
    
    def extract_csv_metadata(
        self,
        file_path: str,
        user_id: int,
        job_id: int
    ) -> list[dict]:
        """Extract metadata from CSV billing export."""
        metadata_records = []
        
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            # Detect dialect
            sample = f.read(8192)
            f.seek(0)
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
            except csv.Error:
                dialect = csv.excel
            
            reader = csv.DictReader(f, dialect=dialect)
            headers = reader.fieldnames or []
            
            # Detect provider from first row
            first_row = next(reader, None)
            if not first_row:
                return []
            
            provider = self.detect_provider(headers, first_row)
            field_mapping = self._get_field_mapping(provider)
            
            # Process first row
            records = self._process_row(first_row, headers, field_mapping, provider, user_id, job_id)
            metadata_records.extend(records)
            
            # Process remaining rows
            row_count = 1
            for row in reader:
                if row_count >= 10000:  # Limit for demo, process in chunks in production
                    break
                records = self._process_row(row, headers, field_mapping, provider, user_id, job_id)
                metadata_records.extend(records)
                row_count += 1
        
        return metadata_records
    
    def _get_field_mapping(self, provider: str) -> dict:
        """Get field mapping for a provider."""
        mappings = {
            CloudProvider.AWS.value: self.AWS_BILLING_FIELDS,
            CloudProvider.GCP.value: self.GCP_BILLING_FIELDS,
            CloudProvider.AZURE.value: self.AZURE_BILLING_FIELDS,
        }
        return mappings.get(provider, {})
    
    def _process_row(
        self,
        row: dict,
        headers: list[str],
        field_mapping: dict,
        provider: str,
        user_id: int,
        job_id: int
    ) -> list[dict]:
        """Process a single data row into metadata records."""
        records = []
        
        # Map fields
        mapped = {}
        for raw_key, mapped_key in field_mapping.items():
            if raw_key in row:
                mapped[mapped_key] = row[raw_key]
        
        # Skip if no resource_id
        resource_id = mapped.get('resource_id', '').strip()
        if not resource_id:
            return records
        
        # Determine entity type from service_type
        service_type = mapped.get('service_type', '').upper()
        entity_type = self._determine_entity_type(service_type)
        
        # Extract attributes
        attributes = self._extract_attributes(mapped, service_type, provider)
        
        # Extract tags
        tags = self._extract_tags(row)
        
        # Build period timestamps
        period_start = self._parse_timestamp(mapped.get('usage_start'))
        period_end = self._parse_timestamp(mapped.get('usage_end'))
        
        record = {
            'ingestion_job_id': job_id,
            'user_id': user_id,
            'entity_type': entity_type,
            'entity_id': resource_id,
            'provider': provider,
            'region': mapped.get('region'),
            'account_id': mapped.get('account_id'),
            'attributes': attributes,
            'tags': tags,
            'source_path': f'job_{job_id}',
            'raw_data': row,
            'resource_created_at': period_start,
            'resource_updated_at': period_end,
        }
        
        records.append(record)
        return records
    
    def _determine_entity_type(self, service_type: str) -> str:
        """Determine entity type from service type."""
        service_type_upper = service_type.upper()
        
        if any(s in service_type_upper for s in ['S3', 'BUCKET', 'STORAGE', 'BLOB']):
            return 'storage_bucket'
        elif any(s in service_type_upper for s in ['EC2', 'COMPUTE', 'VM', 'INSTANCE']):
            return 'compute_instance'
        elif any(s in service_type_upper for s in ['RDS', 'DATABASE', 'SQL', 'DYNAMODB']):
            return 'database'
        elif any(s in service_type_upper for s in ['LAMBDA', 'FUNCTION', 'SERVERLESS']):
            return 'serverless_function'
        elif any(s in service_type_upper for s in ['VPC', 'LOADBALANCER', 'CDN', 'TRANSFER']):
            return 'network_resource'
        else:
            return 'billing_entry'
    
    def _extract_attributes(self, mapped: dict, service_type: str, provider: str) -> dict:
        """Extract technical attributes from mapped data."""
        attributes = {
            'service_type': service_type,
            'usage_type': mapped.get('usage_type'),
            'operation': mapped.get('operation'),
            'usage_quantity': mapped.get('usage_quantity'),
            'cost_amount': mapped.get('cost_amount'),
            'currency': mapped.get('currency', 'USD'),
        }
        
        # Add provider-specific attributes
        if provider == CloudProvider.AWS.value:
            attributes['availability_zone'] = mapped.get('availability_zone')
        elif provider == CloudProvider.GCP.value:
            attributes['sku_description'] = mapped.get('sku_description')
        elif provider == CloudProvider.AZURE.value:
            attributes['resource_group'] = mapped.get('resource_group')
            attributes['meter_subcategory'] = mapped.get('meter_subcategory')
        
        # Remove None values
        return {k: v for k, v in attributes.items() if v is not None}
    
    def _extract_tags(self, row: dict) -> dict:
        """Extract resource tags from row data."""
        tags = {}
        
        # Look for tag columns in various formats
        for key, value in row.items():
            key_lower = key.lower()
            # AWS: resourceTags/user:Name, user:Environment
            # GCP: labels.key
            # Azure: Tags
            if 'tag' in key_lower or 'label' in key_lower:
                if value:
                    tags[key] = value
        
        return tags
    
    def _parse_timestamp(self, value: Any) -> datetime | None:
        """Parse timestamp from various formats."""
        if not value:
            return None
        
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def compute_checksum(self, file_path: str) -> str:
        """Compute SHA-256 checksum of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def extract_metadata(
        self,
        file_path: str,
        mime_type: str,
        user_id: int,
        job_id: int
    ) -> tuple[list[dict], dict]:
        """
        Extract metadata from a file.
        
        Returns:
            Tuple of (metadata_records, processing_info)
        """
        format_type = self.detect_file_format(file_path, mime_type)
        
        if format_type == 'csv':
            records = self.extract_csv_metadata(file_path, user_id, job_id)
        elif format_type == 'json':
            # TODO: Implement JSON extraction
            records = []
        else:
            records = []
        
        processing_info = {
            'format_detected': format_type,
            'records_extracted': len(records),
            'providers_detected': list(set(r.get('provider') for r in records if r.get('provider'))),
            'entity_types': list(set(r.get('entity_type') for r in records)),
        }
        
        return records, processing_info
