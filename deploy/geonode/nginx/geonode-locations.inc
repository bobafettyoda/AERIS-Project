# AERIS frontend. The trailing slash on proxy_pass strips /aeris/.
location = /aeris {
  return 308 /aeris/;
}

location /aeris/ {
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-Prefix /aeris;
  proxy_pass http://aeris-web:80/;
  proxy_redirect off;
}

# AERIS FastAPI backend. The trailing slash strips /aeris-api/.
location = /aeris-api {
  return 308 /aeris-api/;
}

location /aeris-api/ {
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-Prefix /aeris-api;
  proxy_read_timeout 3600s;
  proxy_send_timeout 3600s;
  proxy_connect_timeout 30s;
  proxy_buffering off;
  proxy_request_buffering off;
  proxy_pass http://aeris-api:8000/;
  proxy_redirect off;
}
