import taskiq_fastapi
import os
import taskiq_redis
import taskiq

from app.middlewares import ErrorHandlerMiddleware

broker = taskiq_redis.RedisStreamBroker(
    url="redis://localhost:6379",
)


env = os.environ.get("ENVIRONMENT")
if env and env == "pytest":
    broker = taskiq.InMemoryBroker(await_inplace=True)


broker.add_middlewares(ErrorHandlerMiddleware())

taskiq_fastapi.init(broker, "app.main:app")