from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    @staticmethod
    def _async_database_url(url: str) -> str:
        """Force the asyncpg driver, whichever postgres scheme is configured."""
        for scheme in ("postgresql+asyncpg://", "postgres://", "postgresql://"):
            if url.startswith(scheme):
                return url if scheme == "postgresql+asyncpg://" else (
                    "postgresql+asyncpg://" + url[len(scheme):]
                )
        return url
        
    async def initialize(self):
        """Initialize database connection pool"""
        try:
            # Create async engine with connection pooling
            database_url = self._async_database_url(settings.database_url)
            
            # Async engines supply their own AsyncAdaptedQueuePool; the sync
            # QueuePool is rejected outright.
            self.engine = create_async_engine(
                database_url,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=3600,  # Recycle connections every hour
                echo=False  # Set to True for SQL debugging
            )
            
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("✅ Database connection pool initialized")
            
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
    
    def get_session(self) -> AsyncSession:
        """Get database session from pool.

        Returns the session itself (not a coroutine) so callers can use it
        directly as an async context manager.
        """
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
