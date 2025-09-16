#!/bin/bash
 
# Production Chat API Test Script - Designed for high-load testing
# Configuration
BASE_URL="http://localhost:8080"
ENDPOINT="/chat/send-message"
TOTAL_REQUESTS=100
CONCURRENT_REQUESTS=100
DELAY_BETWEEN_REQUESTS=0
 
# Test messages array - Production-like queries
messages=(
    "What is DC"
    "latest dc version"
    "What is Email Auto Protector"
    "Give me open tickets for hdfc bank"
    "Share me the details of the ticket with id 97364"
    "What us Garware excel crash isssue?"
    "What is the capital of France?"
    "Who is Paresh Verma?"
    "Create KB for the ticket id 97364, include solution, rca, fix, subject in proper format"
    "Wich client does Mukesh Papanoi handles"
    "How to reset password"
    "What are the latest updates"
    "Show me recent tickets"
    "What is the status of ticket 12345"
    "How do I create a new user"
    "What are the system requirements"
    "How to configure email settings"
    "What is the backup schedule"
    "How to troubleshoot login issues"
    "What are the security policies"
)
 
# Statistics tracking
declare -A stats
stats[total_requests]=0
stats[successful_requests]=0
stats[failed_requests]=0
stats[rate_limit_errors]=0
stats[bedrock_errors]=0
stats[other_errors]=0
stats[start_time]=$(date +%s)
 
# Function to send a single request (no retry logic)
send_request() {
    local message="$1"
    local request_id="$2"
   
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] Sending request $request_id: $message"
   
    # Create a new chat session and extract the session ID
    create_response=$(curl -s -X POST "$BASE_URL/chat/create-chat-session" \
        -H "Content-Type: application/json" \
        -d '{"description": "Production Test", "persona_id": 0}')
    chat_session_id=$(echo "$create_response" | grep -o '"chat_session_id"[ ]*:[ ]*"[^"]*"' | cut -d '"' -f4)
 
    if [ -z "$chat_session_id" ]; then
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$timestamp] ERROR: Failed to create chat session for request $request_id: $create_response"
        ((stats[failed_requests]++))
        return 1
    fi
 
    # Get the response and extract only the HTTP status code
    response=$(curl -s -X POST "$BASE_URL$ENDPOINT" \
        -H "Content-Type: application/json" \
        -H "Accept: text/event-stream" \
        -d "{
            \"message\": \"$message\",
            \"chat_session_id\": \"$chat_session_id\",
            \"prompt_id\": null,
            \"use_existing_user_message\": false,
            \"parent_message_id\": null,
            \"file_descriptors\": [],
            \"search_doc_ids\": null,
            \"retrieval_options\": {
                \"run_search\": \"auto\",
                \"real_time\": true
            }
        }" \
        --max-time 30 \
        -w "Request $request_id - HTTP: %{http_code}, Time: %{time_total}s, Size: %{size_download} bytes\n")
 
    # Extract HTTP status code
    http_code=$(echo "$response" | grep -o "HTTP: [0-9]*" | cut -d ' ' -f2)
    
    # Print only request number and status code
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    if [ "$http_code" = "200" ]; then
        echo "[$timestamp] Request $request_id - Status: $http_code ✅"
        ((stats[successful_requests]++))
    else
        echo "[$timestamp] Request $request_id - Status: $http_code ❌"
        ((stats[failed_requests]++))
    fi
 
    # Check for rate limit error (HTTP 429)
    if [ "$http_code" = "429" ]; then
        ((stats[rate_limit_errors]++))
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$timestamp] ERROR: Rate limit exceeded (HTTP 429) for request $request_id"
        return 1
    fi
 
    # Check for Bedrock token rate limit error
    if echo "$response" | grep -q "Too many tokens, please wait before trying again"; then
        ((stats[bedrock_errors]++))
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$timestamp] ERROR: Bedrock token rate limit exceeded for request $request_id"
        return 1
    fi
 
    # Check for other errors
    if [ "$http_code" != "200" ] && [ "$http_code" != "" ]; then
        ((stats[other_errors]++))
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$timestamp] ERROR: HTTP $http_code for request $request_id"
        return 1
    fi
 
    return 0
}
 
# Function to send requests in parallel with monitoring
send_parallel_requests() {
    local count=$1
    local concurrent=$2
    local delay=$3
   
    echo "Starting production parallel requests: $count total, $concurrent concurrent, ${delay}s delay"
    echo "=================================================="
   
    # Create a temporary file to store PIDs
    temp_file=$(mktemp)
   
    for ((i=1; i<=count; i++)); do
        # Get a random message from the array
        message_index=$((RANDOM % ${#messages[@]}))
        message="${messages[$message_index]}"
       
        # Send request in background
        send_request "$message" "$i" &
       
        # Store PID
        echo $! >> "$temp_file"
        ((stats[total_requests]++))
       
        # Add delay between requests to avoid overwhelming the system
        sleep $delay
       
        # Limit concurrent requests
        if ((i % concurrent == 0)); then
            echo "Waiting for batch $((i/concurrent)) to complete..."
            # Wait for all background processes in current batch
            while read -r pid; do
                wait "$pid" 2>/dev/null
            done < "$temp_file"
            # Clear the temp file for next batch
            > "$temp_file"
            # Add extra delay between batches
            sleep 2
        fi
    done
   
    # Wait for remaining processes
    echo "Waiting for remaining requests to complete..."
    while read -r pid; do
        wait "$pid" 2>/dev/null
    done < "$temp_file"
   
    # Clean up
    rm "$temp_file"
   
    echo "=================================================="
    echo "All requests completed!"
}
 
# Function to print statistics
print_stats() {
    local end_time=$(date +%s)
    local duration=$((end_time - stats[start_time]))
    local success_rate=$(echo "scale=2; ${stats[successful_requests]} * 100 / ${stats[total_requests]}" | bc -l 2>/dev/null || echo "0")
   
    echo ""
    echo "=================================================="
    echo "LOAD TEST STATISTICS"
    echo "=================================================="
    echo "Total Requests: ${stats[total_requests]}"
    echo "Successful: ${stats[successful_requests]}"
    echo "Failed: ${stats[failed_requests]}"
    echo "Success Rate: ${success_rate}%"
    echo ""
    echo "Error Breakdown:"
    echo "- Rate Limit (429): ${stats[rate_limit_errors]}"
    echo "- Bedrock Errors: ${stats[bedrock_errors]}"
    echo "- Other Errors: ${stats[other_errors]}"
    echo ""
    echo "Duration: ${duration}s"
    echo "Avg RPS: $(echo "scale=2; ${stats[total_requests]} / $duration" | bc -l 2>/dev/null || echo "0")"
    echo "=================================================="
}
 
# Function to check system health
check_system_health() {
    echo "Checking system health..."
   
    # Check if API server is responding
    health_check=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" 2>/dev/null)
    if [ "$health_check" = "200" ]; then
        echo "✓ API server is healthy"
    else
        echo "✗ API server health check failed (HTTP $health_check)"
        return 1
    fi
   
    # Check if we can create a chat session
    test_session=$(curl -s -X POST "$BASE_URL/chat/create-chat-session" \
        -H "Content-Type: application/json" \
        -d '{"description": "Health Check", "persona_id": 0}')
   
    if echo "$test_session" | grep -q '"chat_session_id"'; then
        echo "✓ Chat session creation is working"
    else
        echo "✗ Chat session creation failed (Auth required or service unavailable)"
        echo "Note: This test requires authentication to be disabled or valid credentials"
        return 1
    fi
   
    echo "System health check passed"
    return 0
}
 
# Main execution
echo "Production Chat API Test Script - High Load Testing"
echo "=================================================="
echo "Base URL: $BASE_URL"
echo "Endpoint: $ENDPOINT"
echo "Total requests: $TOTAL_REQUESTS"
echo "Concurrent requests: $CONCURRENT_REQUESTS"
echo "Delay between requests: ${DELAY_BETWEEN_REQUESTS}s"
echo "No retry logic - requests fail immediately on error"
echo ""
 
# Check if curl is available
if ! command -v curl &> /dev/null; then
    echo "Error: curl is not installed"
    exit 1
fi
 
# Check if bc is available for calculations
if ! command -v bc &> /dev/null; then
    echo "Warning: bc not found, some statistics may not display correctly"
fi
 
# Check system health before starting
if ! check_system_health; then
    echo "System health check failed. Aborting test."
    exit 1
fi
 
# Menu for different test options
echo "Choose test type:"
echo "1. Production load test (default)"
echo "2. Stress test (higher concurrency)"
echo "3. Custom configuration"
read -p "Enter choice (1-3): " choice
 
case $choice in
    1|"")
        echo "Running production load test..."
        send_parallel_requests $TOTAL_REQUESTS $CONCURRENT_REQUESTS $DELAY_BETWEEN_REQUESTS
        ;;
    2)
        echo "Running stress test..."
        send_parallel_requests 100 20 0.5
        ;;
    3)
        read -p "Enter total number of requests: " TOTAL_REQUESTS
        read -p "Enter concurrent requests: " CONCURRENT_REQUESTS
        read -p "Enter delay between requests in seconds: " DELAY_BETWEEN_REQUESTS
        send_parallel_requests $TOTAL_REQUESTS $CONCURRENT_REQUESTS $DELAY_BETWEEN_REQUESTS
        ;;
    *)
        echo "Invalid choice. Running production load test..."
        send_parallel_requests $TOTAL_REQUESTS $CONCURRENT_REQUESTS $DELAY_BETWEEN_REQUESTS
        ;;
esac
 
# Print final statistics
print_stats
 
echo ""
echo "Test completed!"