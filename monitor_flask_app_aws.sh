#!/bin/bash
# Monitoring script for AWS EC2 Flask app deployment

set -e

# Configuration
REGION="us-east-2"
KEY_NAME="guestrix-key-pair"
DOMAIN="dev.guestrix.ai"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_message() {
    echo -e "${GREEN}[INFO] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

print_header() {
    echo -e "${BLUE}[MONITOR] $1${NC}"
}

# Function to get instance info
get_instance_info() {
    local instance_info=$(aws ec2 describe-instances --region $REGION \
        --filters "Name=tag:Name,Values=guestrix-flask-dev" "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].[InstanceId,PublicDnsName,PublicIpAddress,State.Name]' \
        --output text 2>/dev/null)
    
    if [ "$instance_info" = "None" ] || [ -z "$instance_info" ]; then
        print_error "No running instance found with tag 'guestrix-flask-dev'"
        return 1
    fi
    
    echo "$instance_info"
}

# Function to check instance status
check_instance_status() {
    print_header "Checking EC2 Instance Status"
    
    local instance_info=$(get_instance_info)
    if [ $? -ne 0 ]; then
        return 1
    fi
    
    local instance_id=$(echo "$instance_info" | awk '{print $1}')
    local instance_dns=$(echo "$instance_info" | awk '{print $2}')
    local instance_ip=$(echo "$instance_info" | awk '{print $3}')
    local instance_state=$(echo "$instance_info" | awk '{print $4}')
    
    print_message "Instance ID: $instance_id"
    print_message "Instance DNS: $instance_dns"
    print_message "Instance IP: $instance_ip"
    print_message "Instance State: $instance_state"
    
    # Export for use in other functions
    export INSTANCE_DNS="$instance_dns"
    export INSTANCE_ID="$instance_id"
    export INSTANCE_IP="$instance_ip"
}

# Function to check SSH connectivity
check_ssh() {
    print_header "Checking SSH Connectivity"
    
    if [ -z "$INSTANCE_DNS" ]; then
        print_error "Instance DNS not available. Run status check first."
        return 1
    fi
    
    if ssh -i "concierge/infra/$KEY_NAME.pem" -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=accept-new ec2-user@$INSTANCE_DNS "echo SSH connection successful" &> /dev/null; then
        print_message "SSH connection: OK"
        return 0
    else
        print_error "SSH connection: FAILED"
        return 1
    fi
}

# Function to check application services
check_services() {
    print_header "Checking Application Services"
    
    if [ -z "$INSTANCE_DNS" ]; then
        print_error "Instance DNS not available. Run status check first."
        return 1
    fi
    
    ssh -i "concierge/infra/$KEY_NAME.pem" ec2-user@$INSTANCE_DNS "
        echo 'Checking Nginx status:'
        sudo systemctl is-active nginx && echo 'Nginx: RUNNING' || echo 'Nginx: STOPPED'
        
        echo 'Checking Dashboard service status:'
        sudo systemctl is-active dashboard && echo 'Dashboard: RUNNING' || echo 'Dashboard: STOPPED'
        
        echo 'Checking listening ports:'
        sudo netstat -tlnp | grep -E ':(80|443|8080)'
    "
}

# Function to check application logs
check_logs() {
    print_header "Checking Application Logs"
    
    if [ -z "$INSTANCE_DNS" ]; then
        print_error "Instance DNS not available. Run status check first."
        return 1
    fi
    
    local log_type=${1:-"recent"}
    
    case $log_type in
        "recent")
            print_message "Showing recent logs (last 20 lines)..."
            ssh -i "concierge/infra/$KEY_NAME.pem" ec2-user@$INSTANCE_DNS "
                echo '=== Dashboard Service Logs ==='
                sudo journalctl -u dashboard --no-pager -n 20
                echo ''
                echo '=== Nginx Error Logs ==='
                sudo tail -n 10 /var/log/nginx/error.log 2>/dev/null || echo 'No nginx error logs found'
                echo ''
                echo '=== Gunicorn Error Logs ==='
                sudo tail -n 10 /var/log/dashboard.error.log 2>/dev/null || echo 'No gunicorn error logs found'
            "
            ;;
        "full")
            print_message "Showing full logs..."
            ssh -i "concierge/infra/$KEY_NAME.pem" ec2-user@$INSTANCE_DNS "
                echo '=== Dashboard Service Logs ==='
                sudo journalctl -u dashboard --no-pager
            "
            ;;
        "errors")
            print_message "Showing error logs only..."
            ssh -i "concierge/infra/$KEY_NAME.pem" ec2-user@$INSTANCE_DNS "
                echo '=== Dashboard Service Errors ==='
                sudo journalctl -u dashboard --no-pager -p err
                echo ''
                echo '=== Nginx Error Logs ==='
                sudo cat /var/log/nginx/error.log 2>/dev/null || echo 'No nginx error logs found'
                echo ''
                echo '=== Gunicorn Error Logs ==='
                sudo cat /var/log/dashboard.error.log 2>/dev/null || echo 'No gunicorn error logs found'
            "
            ;;
    esac
}

# Function to check system resources
check_resources() {
    print_header "Checking System Resources"
    
    if [ -z "$INSTANCE_DNS" ]; then
        print_error "Instance DNS not available. Run status check first."
        return 1
    fi
    
    ssh -i "concierge/infra/$KEY_NAME.pem" ec2-user@$INSTANCE_DNS "
        echo 'System uptime:'
        uptime
        echo ''
        echo 'Memory usage:'
        free -h
        echo ''
        echo 'Disk usage:'
        df -h
        echo ''
        echo 'CPU usage:'
        top -bn1 | grep 'Cpu(s)' | awk '{print \$2}' | sed 's/%us,//'
        echo ''
        echo 'Top processes by memory:'
        ps aux --sort=-%mem | head -10
    "
}

# Function to test HTTP connectivity
test_http() {
    print_header "Testing HTTP Connectivity"
    
    if [ -z "$INSTANCE_IP" ]; then
        print_error "Instance IP not available. Run status check first."
        return 1
    fi
    
    print_message "Testing HTTP connection to $INSTANCE_IP..."
    if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "http://$INSTANCE_IP" | grep -q "200\|301\|302"; then
        print_message "HTTP connection: OK"
    else
        print_warning "HTTP connection: FAILED or redirected"
    fi
    
    print_message "Testing HTTPS connection to $DOMAIN..."
    if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "https://$DOMAIN" | grep -q "200"; then
        print_message "HTTPS connection to $DOMAIN: OK"
    else
        print_warning "HTTPS connection to $DOMAIN: FAILED"
        print_message "This might be expected if DNS is not yet configured"
    fi
}

# Function to restart services
restart_services() {
    print_header "Restarting Services"
    
    if [ -z "$INSTANCE_DNS" ]; then
        print_error "Instance DNS not available. Run status check first."
        return 1
    fi
    
    print_warning "This will restart the Flask application and Nginx..."
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ssh -i "concierge/infra/$KEY_NAME.pem" ec2-user@$INSTANCE_DNS "
            echo 'Restarting Dashboard service...'
            sudo systemctl restart dashboard
            echo 'Restarting Nginx...'
            sudo systemctl restart nginx
            echo 'Services restarted successfully'
        "
        print_message "Services restarted successfully"
    else
        print_message "Operation cancelled"
    fi
}

# Main function
main() {
    case "${1:-status}" in
        "status")
            check_instance_status
            if [ $? -eq 0 ]; then
                check_ssh
                check_services
                test_http
            fi
            ;;
        "logs")
            check_instance_status && check_logs "${2:-recent}"
            ;;
        "resources")
            check_instance_status && check_resources
            ;;
        "restart")
            check_instance_status && restart_services
            ;;
        "ssh")
            check_instance_status && ssh -i "concierge/infra/$KEY_NAME.pem" ec2-user@$INSTANCE_DNS
            ;;
        *)
            echo "Usage: $0 {status|logs [recent|full|errors]|resources|restart|ssh}"
            echo ""
            echo "Commands:"
            echo "  status     - Check instance and service status (default)"
            echo "  logs       - Show application logs"
            echo "  resources  - Show system resource usage"
            echo "  restart    - Restart application services"
            echo "  ssh        - SSH into the instance"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
