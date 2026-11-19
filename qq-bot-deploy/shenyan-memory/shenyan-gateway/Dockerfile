FROM docker.1ms.run/soulter/astrbot:latest
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# 网关本体 + MCP 客户端 + 自带的 world server。
# 不装官方 MCP SDK：基础镜像里锁了 pydantic，装进去会打架；协议是纯 JSON-RPC，自己实现零依赖。
COPY app.py actions.py stickers.py world.py mcp_stdio.py world_server.py ./

USER 10001
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
