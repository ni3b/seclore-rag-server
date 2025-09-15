#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Gitea Configuration
GITEA_USERNAME="Abhijit.chaudhry"
GITEA_TOKEN="397343da3e1ba8bd7bf2b704c7759313fc6fbd7e"
GITEA_URL="git.seclore.com"
REGISTRY_URL="${GITEA_URL}/automation"

# Function to print colored messages
print_message() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    print_error "docker is not installed. Please install docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Check if docker daemon is running
if ! docker info &> /dev/null; then
    print_error "docker daemon is not running. Please start docker first."
    exit 1
fi

# Login to Gitea container registry
print_message "Logging in to Gitea container registry..."
echo "$GITEA_TOKEN" | docker login $REGISTRY_URL -u $GITEA_USERNAME --password-stdin

if [ $? -ne 0 ]; then
    print_error "Failed to login to Gitea container registry"
    exit 1
fi

# Build images using docker-compose
print_message "Building images using docker-compose..."
docker-compose -f deployment/docker_compose/seclore/docker-compose.dev.seclore.yml build api_server web_server inference_model_server indexing_model_server

if [ $? -ne 0 ]; then
    print_error "Failed to build images using docker-compose"
    exit 1
fi

# Tag and push backend image
print_message "Tagging and pushing backend image..."
docker tag onyxdotapp/onyx-backend:latest $REGISTRY_URL/onyx-backend:latest
docker push $REGISTRY_URL/onyx-backend:latest

if [ $? -ne 0 ]; then
    print_error "Failed to push backend image"
    exit 1
fi

# Tag and push web server image
print_message "Tagging and pushing web server image..."
docker tag onyxdotapp/onyx-web-server:latest $REGISTRY_URL/onyx-web-server:latest
docker push $REGISTRY_URL/onyx-web-server:latest

if [ $? -ne 0 ]; then
    print_error "Failed to push web server image"
    exit 1
fi

# Tag and push model server image
print_message "Tagging and pushing model server image..."
docker tag onyxdotapp/onyx-model-server:latest $REGISTRY_URL/onyx-model-server:latest
docker push $REGISTRY_URL/onyx-model-server:latest

if [ $? -ne 0 ]; then
    print_error "Failed to push model server image"
    exit 1
fi

print_message "All images pushed successfully to Gitea container registry!"

# Optional: Ask if user wants to clean up old images
read -p "Do you want to remove old images? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_message "Removing old images..."
    docker rmi $(docker images | grep onyxdotapp | grep -v latest | awk '{print $3}')
    print_message "Old images removed successfully!"
fi

print_message "Build and push process completed!"