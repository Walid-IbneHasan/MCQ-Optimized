"""
# Complete API Endpoints Reference

## Authentication Endpoints

### POST /auth/register/
Register a new user account.

**Request:**
```json
{
  "phone_number": "01712345678",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com"
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "Registration successful. OTP sent to your phone.",
  "phone_number": "01712345678"
}
```

### POST /auth/verify-otp/
Verify OTP code sent via SMS.

**Request:**
```json
{
  "phone_number": "01712345678",
  "otp_code": "123456",
  "otp_type": "registration"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "OTP verified successfully.",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": "uuid-here",
    "phone_number": "01712345678",
    "full_name": "John Doe",
    "role": "student"
  }
}
```

### POST /auth/login/
Login with phone number and password.

**Request:**
```json
{
  "phone_number": "01712345678",
  "password": "SecurePass123!"
}
```

**Response (200):**
```json
{
  "success": true,
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": "uuid-here",
    "phone_number": "01712345678",
    "full_name": "John Doe",
    "role": "student"
  }
}
```

### POST /auth/token/refresh/
Refresh JWT access token.

**Request:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response (200):**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

## Exam Endpoints

### GET /exams/exams/
List available exams with filtering.

**Query Parameters:**
- `type`: Filter by exam type (`self_paced`, `scheduled`, `practice`)
- `subject`: Filter by subject ID
- `search`: Search in title and description

**Response (200):**
```json
{
  "success": true,
  "count": 25,
  "next": "http://localhost:8000/api/exams/exams/?page=2",
  "previous": null,
  "results": [
    {
      "id": "exam-uuid",
      "title": "Mathematics Chapter 1 Test",
      "description": "Test covering basic algebra concepts",
      "exam_type": "self_paced",
      "total_questions": 50,
      "duration_minutes": 60,
      "marks_per_question": 1.0,
      "negative_marking_enabled": true,
      "negative_marks": 0.25,
      "passing_percentage": 60.0,
      "can_start_now": true,
      "chapters_count": 2,
      "average_score": 72.5,
      "total_attempts": 1250
    }
  ]
}
```

### POST /exams/exams/{id}/start_exam/
Start an exam session.

**Request:**
```json
{
  "exam_id": "exam-uuid",
  "custom_duration": 45
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "Exam started successfully",
  "session": {
    "id": "session-uuid",
    "exam_detail": {
      "id": "exam-uuid",
      "title": "Mathematics Chapter 1 Test",
      "total_questions": 50
    },
    "status": "in_progress",
    "duration_minutes": 45,
    "time_remaining_seconds": 2700,
    "started_at": "2024-01-15T10:30:00Z"
  }
}
```

### GET /exams/sessions/{id}/questions/
Get questions for active exam session.

**Response (200):**
```json
{
  "success": true,
  "session": {
    "id": "session-uuid",
    "status": "in_progress",
    "time_remaining_seconds": 2400
  },
  "questions": [
    {
      "question_number": 1,
      "question_detail": {
        "id": "question-uuid",
        "question_text": "What is 2 + 2?",
        "question_image": null,
        "difficulty": "easy",
        "marks": 1.0
      },
      "options": [
        {
          "id": "option-uuid-1",
          "option_text": "3",
          "option_order": 1
        },
        {
          "id": "option-uuid-2",
          "option_text": "4",
          "option_order": 2
        },
        {
          "id": "option-uuid-3",
          "option_text": "5",
          "option_order": 3
        },
        {
          "id": "option-uuid-4",
          "option_text": "6",
          "option_order": 4
        }
      ]
    }
  ]
}
```

### POST /exams/sessions/{id}/save_answer/
Save answer during exam session.

**Request:**
```json
{
  "question_id": "question-uuid",
  "selected_option_id": "option-uuid-2",
  "time_spent_seconds": 45,
  "is_marked_for_review": false
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Answer saved successfully"
}
```

### POST /exams/exams/submit_exam/
Submit completed exam.

**Request:**
```json
{
  "session_id": "session-uuid",
  "answers": [
    {
      "question_id": "question-uuid-1",
      "selected_option_id": "option-uuid-2",
      "time_spent_seconds": 45,
      "is_marked_for_review": false
    },
    {
      "question_id": "question-uuid-2",
      "selected_option_id": null,
      "time_spent_seconds": 30,
      "is_marked_for_review": true
    }
  ]
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Exam submitted successfully",
  "session": {
    "id": "session-uuid",
    "status": "completed",
    "total_score": 85.5,
    "percentage_score": 85.5,
    "is_passed": true
  }
}
```

## Results Endpoints

### GET /results/exam-results/my_results/
Get user's exam results with analytics.

**Response (200):**
```json
{
  "success": true,
  "summary": {
    "total_exams": 15,
    "passed_exams": 12,
    "pass_rate": 80.0,
    "average_score": 76.8
  },
  "subject_performance": [
    {
      "subject_detail": {
        "name": "Mathematics",
        "id": "subject-uuid"
      },
      "exams_taken": 8,
      "pass_rate": 87.5,
      "average_score": 81.2,
      "trend": "improving"
    }
  ],
  "results": [
    {
      "id": "result-uuid",
      "exam_detail": {
        "title": "Mathematics Test",
        "id": "exam-uuid"
      },
      "percentage_score": 85.5,
      "is_passed": true,
      "grade": "A",
      "total_questions": 50,
      "correct_answers": 42,
      "wrong_answers": 6,
      "unanswered": 2,
      "time_taken_minutes": 45,
      "performance_rating": "Very Good",
      "weak_areas": ["Quadratic Equations"],
      "strong_areas": ["Linear Algebra", "Geometry"],
      "created_at": "2024-01-15T12:00:00Z"
    }
  ]
}
```

### GET /results/exam-results/{id}/detailed_analysis/
Get detailed analysis for specific result.

**Response (200):**
```json
{
  "success": true,
  "result": {
    "id": "result-uuid",
    "percentage_score": 85.5,
    "subject_wise_scores": {
      "Algebra": {
        "correct": 15,
        "total": 20,
        "percentage": 75.0
      },
      "Geometry": {
        "correct": 27,
        "total": 30,
        "percentage": 90.0
      }
    },
    "difficulty_wise_scores": {
      "easy": 92.0,
      "medium": 80.0,
      "hard": 65.0
    }
  },
  "question_analysis": [
    {
      "question_id": "question-uuid-1",
      "question_text": "Solve: 2x + 3 = 7",
      "is_correct": true,
      "selected_option": "x = 2",
      "correct_answer": "x = 2",
      "marks_awarded": 1.0,
      "time_spent": 30,
      "difficulty": "easy",
      "chapter": "Linear Equations",
      "explanation": "Subtract 3 from both sides, then divide by 2"
    }
  ],
  "session_stats": {
    "total_time": 2700,
    "tab_switches": 2,
    "suspicious_activities": 0
  }
}
```

## Leaderboards Endpoints

### GET /leaderboards/leaderboards/
List leaderboards with filtering.

**Query Parameters:**
- `scope`: Filter by scope (`global`, `subject`, `chapter`, `exam`)
- `period`: Filter by period (`daily`, `weekly`, `monthly`, `all_time`)
- `current`: Show only current period (`true`/`false`)

**Response (200):**
```json
{
  "success": true,
  "leaderboards": [
    {
      "id": "leaderboard-uuid",
      "leaderboard_type_detail": {
        "name": "Global Monthly Rankings",
        "scope": "global",
        "period": "monthly"
      },
      "period_start": "2024-01-01T00:00:00Z",
      "period_end": "2024-02-01T00:00:00Z",
      "total_participants": 1250,
      "is_current_period": true,
      "top_entries": [
        {
          "user_id": "user-uuid-1",
          "user_name": "John Doe",
          "rank": 1,
          "score": 92.5,
          "total_exams": 15
        },
        {
          "user_id": "user-uuid-2", 
          "user_name": "Jane Smith",
          "rank": 2,
          "score": 89.3,
          "total_exams": 12
        }
      ]
    }
  ]
}
```

### GET /leaderboards/leaderboards/my_rankings/
Get current user's rankings across leaderboards.

**Response (200):**
```json
{
  "success": true,
  "my_rankings": {
    "Global Monthly Rankings": [
      {
        "leaderboard_id": "leaderboard-uuid",
        "rank": 15,
        "score": 78.5,
        "total_participants": 1250,
        "rank_change": 3,
        "performance_trend": "improving"
      }
    ],
    "Mathematics Subject Rankings": [
      {
        "leaderboard_id": "leaderboard-uuid-2",
        "rank": 8,
        "score": 82.1,
        "total_participants": 450,
        "subject": "Mathematics",
        "rank_change": -2,
        "performance_trend": "stable"
      }
    ]
  }
}
```

## Subscription Endpoints

### GET /subscriptions/plans/
List available subscription plans.

**Response (200):**
```json
{
  "success": true,
  "results": [
    {
      "id": "plan-uuid",
      "name": "Basic Plan",
      "description": "Perfect for regular practice",
      "price": "200.00",
      "currency": "BDT",
      "exam_limit": 10,
      "duration_days": 30,
      "allows_scheduled_exams": true,
      "allows_unlimited_retakes": true,
      "includes_analytics": true
    },
    {
      "id": "plan-uuid-2",
      "name": "Premium Plan", 
      "description": "Unlimited access with advanced features",
      "price": "500.00",
      "currency": "BDT",
      "exam_limit": 30,
      "duration_days": 120,
      "allows_scheduled_exams": true,
      "allows_unlimited_retakes": true,
      "includes_analytics": true
    }
  ]
}
```

### POST /subscriptions/subscriptions/purchase/
Purchase a subscription plan.

**Request:**
```json
{
  "plan_id": "plan-uuid",
  "payment_gateway": "sslcommerz",
  "success_url": "https://yoursite.com/success",
  "cancel_url": "https://yoursite.com/cancel"
}
```

**Response (201):**
```json
{
  "success": true,
  "payment_url": "https://sandbox.sslcommerz.com/gwprocess/v4/api.php?Q=pay&SESSIONKEY=...",
  "transaction_id": "TXN1640995200123",
  "subscription_id": "subscription-uuid"
}
```

### GET /subscriptions/subscriptions/active/
Get user's active subscription.

**Response (200):**
```json
{
  "success": true,
  "subscription": {
    "id": "subscription-uuid",
    "plan_detail": {
      "name": "Basic Plan",
      "exam_limit": 10,
      "duration_days": 30
    },
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-01-31T23:59:59Z",
    "exams_used": 3,
    "exams_remaining": 7,
    "days_remaining": 15,
    "is_active": true,
    "payment_status": "completed"
  }
}
```

## Analytics Endpoints

### GET /analytics/analytics/dashboard/
Get comprehensive analytics dashboard (Admin only).

**Response (200):**
```json
{
  "success": true,
  "dashboard": {
    "users": {
      "total": 5420,
      "active_today": 342,
      "new_today": 15
    },
    "exams": {
      "total_taken": 12450,
      "taken_today": 156,
      "completed_today": 142,
      "completion_rate_today": 91.0
    },
    "performance": {
      "average_score_today": 74.8
    },
    "subscriptions": {
      "active": 1200,
      "new_today": 8,
      "revenue_today": 2400.00
    }
  }
}
```

## WebSocket API Reference

### Connection
```javascript
// Exam session WebSocket
const examSocket = new WebSocket(
  `ws://localhost:8000/ws/exam/${sessionId}/?token=${jwtToken}`
);

// Timer WebSocket  
const timerSocket = new WebSocket(
  `ws://localhost:8000/ws/exam-timer/${sessionId}/?token=${jwtToken}`
);
```

### Message Types

#### Client → Server
```javascript
// Heartbeat (every 30 seconds)
{
  "type": "heartbeat",
  "timestamp": 1640995200000
}

// Save answer
{
  "type": "save_answer",
  "question_id": "question-uuid",
  "selected_option_id": "option-uuid",
  "time_spent_seconds": 45,
  "is_marked_for_review": false
}

// Report tab switching (anti-cheat)
{
  "type": "tab_switch", 
  "timestamp": 1640995200000,
  "away_duration": 3000
}
```

#### Server → Client
```javascript
// Session update
{
  "type": "session_update",
  "session_id": "session-uuid",
  "status": "in_progress", 
  "time_remaining": 1800,
  "answers_submitted": 15,
  "total_questions": 50
}

// Timer update (every second)
{
  "type": "timer_update",
  "time_remaining": 1799,
  "formatted_time": "29:59"
}

// Warning message
{
  "type": "warning",
  "message": "Tab switching detected. Activity is being monitored."
}

// Time expired
{
  "type": "time_up",
  "message": "Time is up! Exam has been auto-submitted."
}
```
"""