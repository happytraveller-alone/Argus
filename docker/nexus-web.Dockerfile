ARG DOCKERHUB_LIBRARY_MIRROR
FROM ${DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library}/nginx:alpine

# 1. 拷贝静态资源到 Nginx 默认 HTML 目录
COPY ./dist /usr/share/nginx/html

# 2. 拷贝配置文件并直接替换 Nginx 主配置
# 注意：构建上下文是 ./nexus-web，所以这里路径直接写 ./nginx.conf
COPY ./nginx.conf /etc/nginx/nginx.conf

# 3. 暴露端口（与配置文件一致）
EXPOSE 5174