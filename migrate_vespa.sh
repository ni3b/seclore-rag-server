#!/bin/bash

# Script to migrate Vespa data between AWS machines
# Usage: ./migrate_vespa.sh <source_host> <destination_host> <ssh_key_path>

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <source_host> <destination_host> <ssh_key_path>"
    echo "Example: $0 ec2-user@source-ip ec2-user@dest-ip ~/.ssh/my-key.pem"
    exit 1
fi

SOURCE_HOST=$1
DEST_HOST=$2
SSH_KEY=$3

# Create a temporary directory for the backup
TEMP_DIR="/tmp/vespa_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p $TEMP_DIR

echo "Starting Vespa data migration..."

# Stop Vespa on source machine
echo "Stopping Vespa on source machine..."
ssh -i $SSH_KEY $SOURCE_HOST "docker stop onyx-stack_index_1"

# Create backup of Vespa data
echo "Creating backup of Vespa data..."
ssh -i $SSH_KEY $SOURCE_HOST "docker run --rm --volumes-from onyx-stack_index_1 -v $TEMP_DIR:/backup vespaengine/vespa tar czf /backup/vespa_data.tar.gz /opt/vespa/var/db/vespa"

# Copy backup to local machine
echo "Copying backup to local machine..."
scp -i $SSH_KEY $SOURCE_HOST:$TEMP_DIR/vespa_data.tar.gz .

# Copy backup to destination machine
echo "Copying backup to destination machine..."
scp -i $SSH_KEY vespa_data.tar.gz $DEST_HOST:$TEMP_DIR/

# Stop Vespa on destination machine
echo "Stopping Vespa on destination machine..."
ssh -i $SSH_KEY $DEST_HOST "docker stop onyx-stack_index_1"

# Restore data on destination machine
echo "Restoring data on destination machine..."
ssh -i $SSH_KEY $DEST_HOST "docker run --rm --volumes-from onyx-stack_index_1 -v $TEMP_DIR:/backup vespaengine/vespa bash -c 'rm -rf /opt/vespa/var/db/vespa/* && tar xzf /backup/vespa_data.tar.gz -C /'"

# Start Vespa on both machines
echo "Starting Vespa on both machines..."
ssh -i $SSH_KEY $SOURCE_HOST "docker start onyx-stack_index_1"
ssh -i $SSH_KEY $DEST_HOST "docker start onyx-stack_index_1"

# Cleanup
echo "Cleaning up temporary files..."
rm vespa_data.tar.gz
ssh -i $SSH_KEY $SOURCE_HOST "rm -rf $TEMP_DIR"
ssh -i $SSH_KEY $DEST_HOST "rm -rf $TEMP_DIR"

echo "Vespa data migration completed successfully!" 