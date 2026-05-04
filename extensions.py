from flask_security import Security, SQLAlchemyUserDatastore
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, default_limits=[], storage_uri="memory://")

# Populated in create_app() after models are imported
user_datastore: SQLAlchemyUserDatastore = None  # type: ignore
security: Security = None                        # type: ignore
