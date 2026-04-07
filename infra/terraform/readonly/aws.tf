locals {
  aws_bucket_arns       = length(var.aws_inventory_bucket_arns) > 0 ? var.aws_inventory_bucket_arns : ["*"]
  aws_bucket_object_arns = [for arn in local.aws_bucket_arns : "${arn}/*"]
}

data "aws_iam_policy_document" "costintel_assume_role" {
  statement {
    sid     = "AllowControlPlaneAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [var.aws_trusted_principal_arn]
    }

    dynamic "condition" {
      for_each = var.aws_external_id != "" ? [1] : []
      content {
        test     = "StringEquals"
        variable = "sts:ExternalId"
        values   = [var.aws_external_id]
      }
    }
  }
}

resource "aws_iam_role" "costintel_readonly" {
  name               = var.aws_role_name
  assume_role_policy = data.aws_iam_policy_document.costintel_assume_role.json
  description        = "Read-only FinOps integration role for CostIntel"
}

# Read-only policy only. No Put/Delete/Update actions.
resource "aws_iam_policy" "costintel_readonly" {
  name        = "${var.aws_role_name}-policy"
  description = "Read-only access for billing, S3 metadata, and pricing catalog"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CostExplorerRead"
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetDimensionValues"
        ]
        Resource = "*"
      },
      {
        Sid    = "PricingCatalogRead"
        Effect = "Allow"
        Action = [
          "pricing:GetProducts"
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ListBucketsReadOnly"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = local.aws_bucket_arns
      },
      {
        Sid    = "S3ObjectReadOnly"
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = local.aws_bucket_object_arns
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "costintel_readonly_attach" {
  role       = aws_iam_role.costintel_readonly.name
  policy_arn = aws_iam_policy.costintel_readonly.arn
}
