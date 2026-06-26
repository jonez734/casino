#!/usr/bin/env python3
"""
Setup script for casino test database.

This script:
1. Adds CHECK constraints to engine.__member and bank.__account to block ':' in member monikers
2. Removes FK constraint from bank.__account
3. Loads the casino schema (creating the house account)

Run with: python scripts/setup_test_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import psycopg

DB_NAME = "zoid6test"


def main():
    conn = psycopg.connect(f"dbname={DB_NAME} user=opencode")
    
    print("Setting up test database for casino...")
    
    # Step 1: Add CHECK constraint to engine.__member (if not exists)
    print("\n1. Adding CHECK constraint to engine.__member...")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT engine.setup_member_constraints()")
        conn.commit()
        print("   ✓ Added member constraint")
    except Exception as e:
        conn.rollback()
        print(f"   ✗ Error: {e}")
    
    # Step 2: Remove FK constraint from bank.__account and add CHECK
    print("\n2. Setting up bank.__account constraints...")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT bank.setup_constraints()")
        conn.commit()
        print("   ✓ Bank constraints configured")
    except Exception as e:
        conn.rollback()
        print(f"   ✗ Error: {e}")
    
    # Step 4: Add overdraft_limit column to bank.__account if not exists
    print("\n4. Adding overdraft_limit column to bank.__account...")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT bank.setup_constraints()")
        conn.commit()
        print("   ✓ Added overdraft_limit column")
    except Exception as e:
        conn.rollback()
        print(f"   ✗ Error: {e}")
    
    # Step 5: Create casino:house account
    print("\n5. Creating casino:house account...")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bank.__account (moniker, balance, maxtransfer, overdraft_limit) 
                VALUES ('casino:house', 0, 1000000, 100000)
                ON CONFLICT (moniker) DO NOTHING
            """)
        conn.commit()
        print("   ✓ Created casino:house account")
    except Exception as e:
        conn.rollback()
        print(f"   ✗ Error: {e}")
    
    # Step 5: Verify
    print("\n5. Verifying setup...")
    with conn.cursor() as cur:
        cur.execute("SELECT moniker, balance FROM bank.__account WHERE moniker = 'casino:house'")
        row = cur.fetchone()
        if row:
            print(f"   ✓ casino:house exists with balance: {row[1]}")
        else:
            print("   ✗ casino:house not found!")
    
    conn.close()
    print("\n✓ Setup complete!")


if __name__ == "__main__":
    main()
