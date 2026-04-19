# Gunicorn configuration file for production deployment
# Optimized for AI-Tutor with parallel request handling

import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
backlog = 2048

# Worker processes
# Use 2-4 workers for better CPU utilization
workers = int(os.getenv('GUNICORN_WORKERS', '4'))

# Worker class - use threads for I/O-bound operations (API calls)
worker_class = 'gthread'
threads = int(os.getenv('GUNICORN_THREADS', '4'))  # 4 threads per worker = up to 16 concurrent requests

# Worker connections
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Timeouts
# Increased timeout for AI API calls (DeepSeek can take 10-30 seconds)
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'formyla'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None

# Preload app for better memory usage
preload_app = True

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    print("🚀 Starting Gunicorn server...")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    print("🔄 Reloading Gunicorn workers...")

def when_ready(server):
    """Called just after the server is started."""
    print(f"✅ Gunicorn ready with {workers} workers × {threads} threads = {workers * threads} concurrent requests")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    print(f"⚠️  Worker {worker.pid} interrupted")

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    print(f"❌ Worker {worker.pid} aborted")
