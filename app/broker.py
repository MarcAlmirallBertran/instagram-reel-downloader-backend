import taskiq_fastapi
import os
from taskiq_redis import RedisStreamBroker
from taskiq import InMemoryBroker


broker = RedisStreamBroker(
    url="redis://localhost:6379",
)


env = os.environ.get("ENVIRONMENT")
if env and env == "pytest":
    broker = InMemoryBroker(await_inplace=True)


taskiq_fastapi.init(broker, "app.main:app")