#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_message() {
    echo -e "${2}${1}${NC}"
}

print_header() {
    echo ""
    print_message "========================================" "$BLUE"
    print_message "$1" "$BLUE"
    print_message "========================================" "$BLUE"
    echo ""
}

print_success() {
    print_message "✓ $1" "$GREEN"
}

print_error() {
    print_message "✗ $1" "$RED"
}

print_warning() {
    print_message "⚠ $1" "$YELLOW"
}

print_info() {
    print_message "→ $1" "$BLUE"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python installation
check_python() {
    print_header "Checking Python Installation"
    
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        print_success "Python is installed: $PYTHON_VERSION"
        
        # Check if version is 3.8 or higher
        REQUIRED_VERSION="3.8"
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
            print_success "Python version is compatible (>= 3.8)"
            return 0
        else
            print_error "Python version must be 3.8 or higher. Current: $PYTHON_VERSION"
            return 1
        fi
    else
        print_error "Python 3 is not installed"
        print_info "Install Python 3: https://www.python.org/downloads/"
        return 1
    fi
}

# Check pip installation
check_pip() {
    print_header "Checking pip Installation"
    
    if command_exists pip3; then
        PIP_VERSION=$(pip3 --version 2>&1 | awk '{print $2}')
        print_success "pip is installed: $PIP_VERSION"
        return 0
    else
        print_error "pip is not installed"
        print_info "Installing pip..."
        python3 -m ensurepip --upgrade
        return $?
    fi
}

# Check Redis installation
check_redis() {
    print_header "Checking Redis Installation"
    
    if command_exists redis-server; then
        REDIS_VERSION=$(redis-server --version 2>&1 | grep -oP 'v=\K[0-9.]+')
        print_success "Redis is installed: $REDIS_VERSION"
        
        # Check if Redis is running
        if redis-cli ping >/dev/null 2>&1; then
            print_success "Redis is running"
            return 0
        else
            print_warning "Redis is installed but not running"
            print_info "Starting Redis..."
            
            # Try to start Redis based on OS
            if [[ "$OSTYPE" == "darwin"* ]]; then
                brew services start redis
            elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                sudo systemctl start redis-server
            fi
            
            sleep 2
            if redis-cli ping >/dev/null 2>&1; then
                print_success "Redis started successfully"
                return 0
            else
                print_error "Failed to start Redis"
                return 1
            fi
        fi
    else
        print_error "Redis is not installed"
        print_info "Install Redis:"
        print_info "  macOS: brew install redis"
        print_info "  Ubuntu/Debian: sudo apt-get install redis-server"
        print_info "  CentOS/RHEL: sudo yum install redis"
        return 1
    fi
}

# Create virtual environment
setup_virtualenv() {
    print_header "Setting Up Virtual Environment"
    
    if [ -d "venv" ]; then
        print_warning "Virtual environment already exists"
        read -p "Do you want to recreate it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Removing existing virtual environment..."
            rm -rf venv
        else
            print_info "Using existing virtual environment"
            return 0
        fi
    fi
    
    print_info "Creating virtual environment..."
    python3 -m venv venv
    
    if [ -d "venv" ]; then
        print_success "Virtual environment created"
        return 0
    else
        print_error "Failed to create virtual environment"
        return 1
    fi
}

# Activate virtual environment
activate_virtualenv() {
    print_header "Activating Virtual Environment"
    
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        print_success "Virtual environment activated"
        return 0
    else
        print_error "Virtual environment not found"
        return 1
    fi
}

# Install requirements
install_requirements() {
    print_header "Installing Python Requirements"
    
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found"
        return 1
    fi
    
    print_info "Upgrading pip..."
    pip install --upgrade pip
    
    print_info "Installing requirements..."
    pip install -r requirements.txt
    
    if [ $? -eq 0 ]; then
        print_success "Requirements installed successfully"
        return 0
    else
        print_error "Failed to install requirements"
        return 1
    fi
}

# Create necessary directories
create_directories() {
    print_header "Creating Necessary Directories"
    
    DIRECTORIES=("logs" "media/documents" "media/news" "media/users/images" "media/announcements/documents" "media/records/documents" "media/records/images" "media/resources/documents")
    
    for dir in "${DIRECTORIES[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_success "Created directory: $dir"
        else
            print_info "Directory already exists: $dir"
        fi
    done
    
    return 0
}

# Run migrations
run_migrations() {
    print_header "Running Database Migrations"
    
    print_info "Making migrations..."
    python manage.py makemigrations
    
    print_info "Applying migrations..."
    python manage.py migrate
    
    if [ $? -eq 0 ]; then
        print_success "Migrations completed successfully"
        return 0
    else
        print_error "Failed to run migrations"
        return 1
    fi
}

# Collect static files
collect_static() {
    print_header "Collecting Static Files"
    
    print_info "Collecting static files..."
    python manage.py collectstatic --noinput
    
    if [ $? -eq 0 ]; then
        print_success "Static files collected successfully"
        return 0
    else
        print_warning "Failed to collect static files (non-critical)"
        return 0
    fi
}

# Create superuser
create_superuser() {
    print_header "Create Superuser (Required)"
    
    read -p "Do you want to create a superuser? (y): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python manage.py createsuperuser
    else
        print_info "Skipping superuser creation"
    fi
}

# Test server
test_server() {
    print_header "Server Check"
    
    print_info "Running Django system check..."
    python manage.py check
    
    if [ $? -eq 0 ]; then
        print_success "Django system check passed"
        return 0
    else
        print_error "Django system check failed"
        return 1
    fi
}

# Display final instructions
display_instructions() {
    print_header "Setup Complete!"
    
    echo ""
    print_success "Your HTA server is ready!"
    echo ""
    print_info "To start the development server:"
    echo "  1. Activate virtual environment: source venv/bin/activate"
    echo "  2. Start Redis (if not running): redis-server"
    echo "  3. Start Django server: python manage.py runserver"
    echo "  4. Start Celery worker: celery -A hta worker -l info"
    echo ""
    print_info "Access your application at: http://localhost:8000"
    print_info "Admin panel: http://localhost:8000/admin"
    echo ""
}

# Main setup function
main() {
    print_message "╔════════════════════════════════════════╗" "$BLUE"
    print_message "║   HTA Server Setup Script             ║" "$BLUE"
    print_message "╚════════════════════════════════════════╝" "$BLUE"
    echo ""
    
    # Run all checks and setup steps
    check_python || exit 1
    check_pip || exit 1
    check_redis || print_warning "Redis check failed - Celery tasks will not work"
    
    setup_virtualenv || exit 1
    activate_virtualenv || exit 1
    install_requirements || exit 1
    
    create_directories
    run_migrations || exit 1
    collect_static
    
    test_server || exit 1
    
    create_superuser
    
    display_instructions
}

# Run main function
main