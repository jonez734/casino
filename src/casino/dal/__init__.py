# casino/dal/__init__.py
# DAL - Data Access Layer
#
# Abstraction layer for database operations. Provides a clean interface
# between business logic (services) and the database. Uses bbsengine6's
# database module for connection pooling and query execution.
#
# Pattern: Services call DAL methods -> DAL executes queries -> Database
# This ensures the UI layer never makes direct database calls.
