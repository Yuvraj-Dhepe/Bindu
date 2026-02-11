# Redis Scheduler

Bindu uses Redis as its distributed task scheduler for coordinating work across multiple workers and processes. The scheduler uses Redis lists with blocking operations for efficient task distribution.

**Scheduler is optional** - InMemoryScheduler is used by default for single-process deployments.

## Configuration

### Environment Variables

Configure Redis connection via environment variables (see `.env.example`):

```bash
# Scheduler Configuration
# Type: "redis" for distributed scheduling or "memory" for single-process
SCHEDULER_TYPE=redis

# Redis connection string
REDIS_URL=rediss://default:<password>@<host>:<port>
```

**Connection String Formats:**

**With password:**
```
rediss://default:password@hostname:port
```

**Without password (local development):**
```
redis://localhost:6379
```

**With database number:**
```
redis://localhost:6379/0
```

**Example:**
```bash
REDIS_URL=rediss://default:mypassword@redis-12345.upstash.io:6379
```

### Agent Configuration

No additional configuration needed in your agent code. Scheduler is configured via environment variables:

```python
config = {
    "author": "your.email@example.com",
    "name": "research_agent",
    "description": "A research assistant agent",
    "deployment": {"url": "http://localhost:3773", "expose": True},
    "skills": ["skills/question-answering", "skills/pdf-processing"],
}

bindufy(config, handler)
```

## Setting Up Redis

### Local Development

#### Using Docker (Recommended)

```bash
# Start Redis container
docker run -d \
  --name bindu-redis \
  -p 6379:6379 \
  redis:7-alpine

# Set environment variable
export REDIS_URL="redis://localhost:6379"
```

#### Using Local Redis

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis

# Set environment variable
export REDIS_URL="redis://localhost:6379"
```

### Cloud Deployment

#### Upstash (Serverless Redis)

1. Create account at [upstash.com](https://upstash.com)
2. Create a new Redis database
3. Copy the connection string (TLS enabled)
4. Set environment variable:
   ```bash
   export REDIS_URL="rediss://default:xxx@xxx.upstash.io:6379"
   ```

## Switching Between Scheduler Types

### From Memory to Redis

1. Set environment variables:
   ```bash
   export SCHEDULER_TYPE=redis
   export REDIS_URL="redis://localhost:6379"
   ```

2. Restart agent

3. Existing in-memory queue is lost (ephemeral)

### From Redis to Memory

1. Update environment:
   ```bash
   export SCHEDULER_TYPE=memory
   # or unset SCHEDULER_TYPE (memory is default)
   ```

2. Restart agent

3. Tasks in Redis queue remain but won't be processed