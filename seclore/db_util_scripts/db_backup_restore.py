import os
import subprocess
import tempfile

# Configuration
CONTAINER_NAME = "onyx-stack_relational_db_1"
LOCAL_DB_NAME = "postgres"
LOCAL_DB_USER = "postgres"
LOCAL_DB_PASSWORD = "password"

RDS_HOST = "database-1.cq1eiiymyenm.us-east-1.rds.amazonaws.com"
RDS_PORT = 5432
RDS_DB_NAME = "postgres"
RDS_USER = "postgres"
RDS_PASSWORD = "password"

def dump_db_to_tempfile():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dump") as tmp_file:
        tmp_path = tmp_file.name
        print(f"Dumping full database from container {CONTAINER_NAME} to {tmp_path}...")

        dump_cmd = [
            "docker", "exec", CONTAINER_NAME,
            "pg_dump",
            "-U", LOCAL_DB_USER,
            "-F", "c",  # Custom format
            "-d", LOCAL_DB_NAME,
            "--no-owner", "--no-privileges"
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = LOCAL_DB_PASSWORD

        with open(tmp_path, "wb") as out_file:
            subprocess.run(dump_cmd, stdout=out_file, check=True, env=env)

        return tmp_path

def restore_to_rds_with_docker(dump_path):
    print(f"Restoring dump to RDS at {RDS_HOST}:{RDS_PORT}...")

    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{os.path.dirname(dump_path)}:/tmp",
        "-e", f"PGPASSWORD={RDS_PASSWORD}",
        "postgres:15",
        "pg_restore",
        "-h", RDS_HOST,
        "-U", RDS_USER,
        "-d", RDS_DB_NAME,
        "-p", str(RDS_PORT),
        "--clean", "--if-exists", "--no-owner", "--no-privileges",
        f"/tmp/{os.path.basename(dump_path)}"
    ]

    subprocess.run(docker_cmd, check=True)

def main():
    dump_file = dump_db_to_tempfile()
    try:
        restore_to_rds_with_docker(dump_file)
        print("✅ Database restore completed successfully.")
    finally:
        if os.path.exists(dump_file):
            os.remove(dump_file)
            print(f"🧹 Removed temporary dump file {dump_file}.")

if __name__ == "__main__":
    main()
