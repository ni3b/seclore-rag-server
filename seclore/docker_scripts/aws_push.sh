#!/bin/bash

# Exit on error
set -e

# Configuration
AWS_REGION="us-east-1"  # Change this to your desired AWS region
AWS_ACCOUNT_ID="1477-0459-8456"  # Will be fetched automatically
ECR_REPOSITORY="seclore-rag-server"
GITEA_REGISTRY="git.seclore.com"
GITEA_REPOSITORY="automation"
IMAGES=("backend" "web-server" "model-server")
AWS_CLI_PATH="/home/ec2-user/.local/bin/aws"  # Absolute path to AWS CLI

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install it first."
    exit 1
fi

# Check if AWS CLI is installed
if [ ! -f "$AWS_CLI_PATH" ]; then
    print_error "AWS CLI is not installed at $AWS_CLI_PATH. Please install it first."
    exit 1
fi

# Get AWS account ID
print_status "Getting AWS account ID..."
AWS_ACCOUNT_ID=$(sudo -u ec2-user $AWS_CLI_PATH sts get-caller-identity --query Account --output text)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    print_error "Failed to get AWS account ID. Please check your AWS credentials."
    exit 1
fi

# Login to ECR
print_status "Logging in to Amazon ECR..."
sudo -u ec2-user $AWS_CLI_PATH ecr get-login-password --region $AWS_REGION | sudo -E docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Function to push an image
push_image() {
    local image_name=$1
    local source_tag="${GITEA_REGISTRY}/${GITEA_REPOSITORY}/onyx-${image_name}:latest"
    local target_tag="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}/onyx-${image_name}:latest"
    
    print_status "Checking if image $source_tag exists..."
    if ! sudo -E docker images | grep -q "${GITEA_REGISTRY}/${GITEA_REPOSITORY}/onyx-${image_name}"; then
        print_error "Image $source_tag not found. Please build it first."
        return 1
    fi
    
    # Create ECR repository if it doesn't exist
    print_status "Ensuring ECR repository exists..."
    sudo -u ec2-user $AWS_CLI_PATH ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region $AWS_REGION || \
    sudo -u ec2-user $AWS_CLI_PATH ecr create-repository --repository-name ${ECR_REPOSITORY} --region $AWS_REGION
    
    print_status "Tagging $source_tag as $target_tag..."
    sudo -E docker tag $source_tag $target_tag
    
    print_status "Pushing $target_tag to ECR..."
    sudo -E docker push $target_tag
    
    print_status "Successfully pushed $target_tag"
}

# Push each image
for image in "${IMAGES[@]}"; do
    print_status "Processing $image..."
    push_image $image
done

print_status "All images have been successfully pushed to ECR!"
print_status "Image URIs:"
for image in "${IMAGES[@]}"; do
    echo "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}/onyx-${image}:latest"
done

# Logout from ECR
print_status "Logging out from ECR..."
sudo -E docker logout $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com