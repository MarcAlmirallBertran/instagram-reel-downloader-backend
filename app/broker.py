import os

import taskiq_fastapi
import taskiq_redis
import taskiq

from app.middlewares import ErrorHandlerMiddleware

from dotenv import load_dotenv
load_dotenv()

broker = taskiq_redis.RedisStreamBroker(
    url="redis://localhost:6379",
)


env = os.environ.get("ENVIRONMENT")
if env and env == "pytest" or env == "local":
    broker = taskiq.InMemoryBroker(await_inplace=True)


broker.add_middlewares(ErrorHandlerMiddleware())

taskiq_fastapi.init(broker, "app.main:app")
