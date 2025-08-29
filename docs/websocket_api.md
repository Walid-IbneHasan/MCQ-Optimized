"""
# WebSocket API Documentation

## Overview
The MCQ Platform uses WebSocket connections for real-time features during exam sessions.

## Authentication
WebSocket connections require authentication via JWT token:
```javascript
const token = 'your-jwt-token';
const socket = new WebSocket(`ws://localhost:8000/ws/exam/${sessionId}/?token=${token}`);
```

## Available Endpoints

### 1. Exam Session WebSocket
**URL:** `ws://localhost:8000/ws/exam/<session_id>/`
**Purpose:** Real-time exam session management and anti-cheat monitoring

#### Client → Server Messages

##### Heartbeat
```json
{
    "type": "heartbeat",
    "timestamp": 1640995200000
}
```

##### Save Answer
```json
{
    "type": "save_answer",
    "question_id": "uuid",
    "selected_option_id": "uuid",
    "time_spent_seconds": 45,
    "is_marked_for_review": false
}
```

##### Tab Switch Detection
```json
{
    "type": "tab_switch",
    "timestamp": 1640995200000,
    "away_duration": 5000
}
```

##### Question Visit
```json
{
    "type": "question_visit",
    "question_number": 5,
    "timestamp": 1640995200000
}
```

#### Server → Client Messages

##### Session Update
```json
{
    "type": "session_update",
    "session_id": "uuid",
    "status": "in_progress",
    "time_remaining": 1800,
    "current_question": 5,
    "answers_submitted": 3,
    "total_questions": 50
}
```

##### Answer Confirmation
```json
{
    "type": "answer_saved",
    "question_id": "uuid",
    "success": true
}
```

##### Warning Messages
```json
{
    "type": "warning",
    "message": "Tab switching detected. This activity is being monitored."
}
```

##### Time Up
```json
{
    "type": "time_up",
    "message": "Time is up! Exam has been auto-submitted."
}
```

### 2. Exam Timer WebSocket
**URL:** `ws://localhost:8000/ws/exam-timer/<session_id>/`
**Purpose:** Dedicated high-frequency timer updates

#### Server → Client Messages

##### Timer Update (Every Second)
```json
{
    "type": "timer_update",
    "time_remaining": 1799,
    "formatted_time": "29:59"
}
```

## Error Handling

### Connection Errors
- Invalid session ID: Connection refused
- Invalid token: Connection closed with code 4001
- Session not active: Connection closed with code 4002

### Message Errors
```json
{
    "type": "error",
    "message": "Invalid message format"
}
```

## Best Practices

1. **Heartbeat**: Send heartbeat every 30 seconds to maintain connection
2. **Error Handling**: Always handle connection errors and reconnection
3. **Message Queuing**: Queue messages if connection is temporarily lost
4. **Graceful Degradation**: Fallback to HTTP polling if WebSocket fails

## Example Implementation

```javascript
class ExamWebSocket {
    constructor(sessionId, token) {
        this.sessionId = sessionId;
        this.token = token;
        this.socket = null;
        this.heartbeatInterval = null;
    }
    
    connect() {
        const url = `ws://localhost:8000/ws/exam/${this.sessionId}/?token=${this.token}`;
        this.socket = new WebSocket(url);
        
        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.startHeartbeat();
        };
        
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };
        
        this.socket.onclose = (event) => {
            console.log('WebSocket closed:', event.code);
            this.stopHeartbeat();
            if (event.code !== 1000) {
                // Reconnect on abnormal closure
                setTimeout(() => this.connect(), 5000);
            }
        };
        
        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }
    
    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            this.send({
                type: 'heartbeat',
                timestamp: Date.now()
            });
        }, 30000);
    }
    
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
    }
    
    send(message) {
        if (this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(message));
        }
    }
    
    handleMessage(data) {
        switch (data.type) {
            case 'session_update':
                this.updateUI(data);
                break;
            case 'warning':
                this.showWarning(data.message);
                break;
            case 'time_up':
                this.handleTimeUp();
                break;
        }
    }
}
```
"""