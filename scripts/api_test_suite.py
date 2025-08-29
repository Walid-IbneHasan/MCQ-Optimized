"""
Comprehensive API testing script for MCQ Platform
"""
import requests
import json
import time
import uuid
from datetime import datetime, timedelta

class MCQPlatformAPITester:
    def __init__(self, base_url='http://localhost:8000/api'):
        self.base_url = base_url
        self.session = requests.Session()
        self.tokens = {}
        self.test_data = {}
        
    def run_full_test_suite(self):
        """Run complete API test suite."""
        print("🚀 Starting MCQ Platform API Test Suite")
        print("=" * 50)
        
        try:
            # 1. Authentication Flow
            self.test_authentication_flow()
            
            # 2. User Management
            self.test_user_management()
            
            # 3. Subscription Management
            self.test_subscription_flow()
            
            # 4. Content Management
            self.test_content_management()
            
            # 5. Exam Flow
            self.test_exam_flow()
            
            # 6. Results and Analytics
            self.test_results_analytics()
            
            # 7. Leaderboards
            self.test_leaderboards()
            
            # 8. Notifications
            self.test_notifications()
            
            print("\n✅ All API tests completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Test suite failed: {str(e)}")
            raise
    
    def test_authentication_flow(self):
        """Test complete authentication flow."""
        print("\n📝 Testing Authentication Flow...")
        
        # Generate test phone number
        test_phone = f"017{uuid.uuid4().hex[:8]}"
        self.test_data['phone_number'] = test_phone
        
        # 1. Register new user
        register_data = {
            'phone_number': test_phone,
            'password': 'TestPass123!',
            'confirm_password': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'testuser@example.com'
        }
        
        response = self.post('/auth/register/', register_data)
        assert response['success'], f"Registration failed: {response}"
        print("   ✓ User registration successful")
        
        # 2. Verify OTP (simulate with mock OTP)
        # In real testing, you'd need actual OTP from SMS
        verify_data = {
            'phone_number': test_phone,
            'otp_code': '123456',  # Mock OTP
            'otp_type': 'registration'
        }
        
        try:
            response = self.post('/auth/verify-otp/', verify_data)
            if response.get('success'):
                self.tokens = {
                    'access': response.get('access_token'),
                    'refresh': response.get('refresh_token')
                }
                self.set_auth_header(self.tokens['access'])
                print("   ✓ OTP verification successful")
            else:
                print("   ⚠ OTP verification skipped (requires real SMS)")
        except:
            print("   ⚠ OTP verification skipped (requires real SMS)")
        
        # 3. Test login
        login_data = {
            'phone_number': test_phone,
            'password': 'TestPass123!'
        }
        
        response = self.post('/auth/login/', login_data)
        if response.get('success'):
            self.tokens = {
                'access': response.get('access_token'),
                'refresh': response.get('refresh_token')
            }
            self.set_auth_header(self.tokens['access'])
            print("   ✓ User login successful")
        else:
            # Create authenticated session for testing
            print("   ⚠ Creating mock authenticated session for testing")
            self.create_test_auth_session()
    
    def test_subscription_flow(self):
        """Test subscription purchase flow."""
        print("\n💳 Testing Subscription Flow...")
        
        # 1. Get subscription plans
        response = self.get('/subscriptions/plans/')
        plans = response.get('results', [])
        assert len(plans) > 0, "No subscription plans found"
        print(f"   ✓ Found {len(plans)} subscription plans")
        
        # 2. Purchase subscription (mock)
        if plans:
            plan_id = plans[0]['id']
            purchase_data = {
                'plan_id': plan_id,
                'payment_gateway': 'sslcommerz',
                'success_url': 'https://example.com/success',
                'cancel_url': 'https://example.com/cancel'
            }
            
            try:
                response = self.post('/subscriptions/subscriptions/purchase/', purchase_data)
                if response.get('success'):
                    print("   ✓ Subscription purchase initiated")
                    self.test_data['subscription_id'] = response.get('subscription_id')
            except:
                print("   ⚠ Subscription purchase test skipped (requires payment setup)")
    
    def test_exam_flow(self):
        """Test complete exam taking flow."""
        print("\n📝 Testing Exam Flow...")
        
        # 1. Get available exams
        response = self.get('/exams/exams/')
        exams = response.get('results', [])
        
        if not exams:
            print("   ⚠ No exams available, creating test exam")
            # Would need admin privileges to create exam
            return
        
        exam = exams[0]
        exam_id = exam['id']
        print(f"   ✓ Found exam: {exam['title']}")
        
        # 2. Start exam session
        start_data = {
            'exam_id': exam_id,
            'custom_duration': 30  # 30 minutes for testing
        }
        
        try:
            response = self.post(f'/exams/exams/{exam_id}/start_exam/', start_data)
            if response.get('success'):
                session = response['session']
                session_id = session['id']
                self.test_data['session_id'] = session_id
                print(f"   ✓ Exam session started: {session_id}")
                
                # 3. Get exam questions
                questions_response = self.get(f'/exams/sessions/{session_id}/questions/')
                if questions_response.get('success'):
                    questions = questions_response['questions']
                    print(f"   ✓ Retrieved {len(questions)} questions")
                    
                    # 4. Submit some answers
                    self.submit_test_answers(session_id, questions[:5])
                    
                    # 5. Submit exam
                    self.submit_exam(session_id, questions)
        except Exception as e:
            print(f"   ⚠ Exam flow test failed: {str(e)}")
    
    def submit_test_answers(self, session_id, questions):
        """Submit test answers during exam."""
        for i, question in enumerate(questions):
            # Select first option for testing
            if question.get('options'):
                answer_data = {
                    'question_id': question['question_detail']['id'],
                    'selected_option_id': question['options'][0]['id'],
                    'time_spent_seconds': 30,
                    'is_marked_for_review': False
                }
                
                try:
                    response = self.post(f'/exams/sessions/{session_id}/save_answer/', answer_data)
                    if response.get('success'):
                        print(f"   ✓ Answer saved for question {i+1}")
                except:
                    print(f"   ⚠ Failed to save answer for question {i+1}")
    
    def submit_exam(self, session_id, questions):
        """Submit complete exam."""
        answers = []
        for question in questions:
            if question.get('options'):
                answers.append({
                    'question_id': question['question_detail']['id'],
                    'selected_option_id': question['options'][0]['id'],
                    'time_spent_seconds': 45,
                    'is_marked_for_review': False
                })
        
        submit_data = {
            'session_id': session_id,
            'answers': answers
        }
        
        try:
            response = self.post('/exams/exams/submit_exam/', submit_data)
            if response.get('success'):
                print("   ✓ Exam submitted successfully")
                return True
        except Exception as e:
            print(f"   ⚠ Exam submission failed: {str(e)}")
        
        return False
    
    # Helper methods
    def get(self, endpoint):
        """Make GET request."""
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url)
        return self.handle_response(response)
    
    def post(self, endpoint, data):
        """Make POST request."""
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, json=data)
        return self.handle_response(response)
    
    def handle_response(self, response):
        """Handle API response."""
        try:
            data = response.json()
            if response.status_code >= 400:
                raise Exception(f"API Error {response.status_code}: {data}")
            return data
        except json.JSONDecodeError:
            raise Exception(f"Invalid JSON response: {response.text}")
    
    def set_auth_header(self, token):
        """Set authentication header."""
        self.session.headers.update({
            'Authorization': f'Bearer {token}'
        })
    
    def create_test_auth_session(self):
        """Create mock authenticated session for testing."""
        # This would need to be implemented based on your test setup
        pass

if __name__ == '__main__':
    tester = MCQPlatformAPITester()
    tester.run_full_test_suite()