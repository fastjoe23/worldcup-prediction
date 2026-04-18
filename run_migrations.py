import os
import psycopg
from pathlib import Path

def run_migrations():
    """Run all SQL migration files in the migrations directory"""
    migrations_dir = Path('migrations')
    
    if not migrations_dir.exists():
        print("No migrations directory found")
        return
    
    migration_files = sorted(migrations_dir.glob('*.sql'))
    
    if not migration_files:
        print("No migration files found")
        return
    
    with psycopg.connect(os.getenv('DATABASE_URL')) as conn:
        with conn.cursor() as cur:
            for migration_file in migration_files:
                print(f"Running migration: {migration_file.name}")
                with open(migration_file, 'r') as f:
                    sql = f.read()
                    cur.execute(sql)
                print(f"✓ {migration_file.name} completed")
        conn.commit()
    
    print("All migrations completed successfully")

if __name__ == '__main__':
    run_migrations()
