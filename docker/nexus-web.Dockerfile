ARG DOCKERHUB_LIBRARY_MIRROR
FROM ${DOCKERHUB_LIBRARY_MIRROR}/nginx:alpine

COPY ./dist /usr/share/nginx/html

# 拷贝 Nginx 配置（确保这个文件在 nexus-web 目录下）
COPY ./nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5174