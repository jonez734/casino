#!/usr/bin/env python3
# casino/tests/test_permissions.py
# Test schema permissions for casino tables/views

import argparse
import os
import sys

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from bbsengine6 import database, io
from casino.dal import player


def main():
    parser = argparse.ArgumentParser(description="Test casino schema permissions")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument(
        "--database", dest="databasename", default="zoid6", help="Database name"
    )
    parser.add_argument(
        "--dbuser", dest="databaseuser", default=os.environ.get("USER", "jam"), help="Database user"
    )
    parser.add_argument(
        "--dbpass", dest="databasepassword", default="", help="Database password"
    )
    parser.add_argument(
        "--dbhost", dest="databasehost", default="localhost", help="Database host"
    )
    parser.add_argument(
        "--dbport", dest="databaseport", default=5432, type=int, help="Database port"
    )
    args = parser.parse_args()

    print(f"Testing permissions on database: {args.databasename} as {args.databaseuser}")

    with database.getpool(args, dbname=args.databasename) as pool:
        with database.connect(args, pool=pool) as conn:
            results = player.test_schema_permissions(args)
            print("\n=== Results ===")
            for table, status in results.items():
                print(f"{table}: {status}")


if __name__ == "__main__":
    main()
