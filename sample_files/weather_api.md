# 城市天气查询 API 服务

一个提供城市天气查询的 REST API，基于 FastAPI + Redis 缓存。

## 接口设计
- GET /api/weather/{city} — 查询指定城市当前天气
- GET /api/forecast/{city}?days=7 — 未来 7 天预报
- 响应格式：{city, temp_c, humidity, condition, updated_at}

## 实现要点
- 数据源：和风天气 API，每 10 分钟刷新一次
- Redis 缓存 TTL 30 分钟，缓存键格式 weather:{city_code}
- 城市名先经过 geocoding 转 city_code，支持模糊匹配中文城市名
- 限流：单 IP 每分钟 60 次

## 部署
Docker Compose 启动（api + redis），监听 8080 端口。
