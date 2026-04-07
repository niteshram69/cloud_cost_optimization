FROM nginx:1.27-alpine

# Remove default configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom configuration
COPY nginx.conf /etc/nginx/conf.d/

# Security: Run as non-root
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d

EXPOSE 80 443

USER nginx

CMD ["nginx", "-g", "daemon off;"]
