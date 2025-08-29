from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from .models import OTPVerification
from datetime import timedelta
from django.utils import timezone

User = get_user_model()

class UserModelTest(TestCase):
    """
    Test User model functionality.
    """
    
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number='01712345678',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
    
    def test_user_creation(self):
        """Test user creation."""
        self.assertEqual(self.user.phone_number, '01712345678')
        self.assertTrue(self.user.check_password('testpass123'))
        self.assertEqual(self.user.full_name, 'Test User')
        self.assertEqual(self.user.role, 'student')
        self.assertFalse(self.user.is_active)
    
    def test_user_string_representation(self):
        """Test user string representation."""
        self.assertEqual(str(self.user), '01712345678')
    
    def test_user_permissions(self):
        """Test user permission methods."""
        self.assertFalse(self.user.is_admin)
        self.assertFalse(self.user.is_teacher_or_above)
        
        self.user.role = 'admin'
        self.user.save()
        self.assertTrue(self.user.is_admin)
        self.assertTrue(self.user.is_teacher_or_above)

class AuthenticationAPITest(APITestCase):
    """
    Test authentication API endpoints.
    """
    
    def setUp(self):
        self.registration_data = {
            'phone_number': '01712345678',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User'
        }
    
    def test_user_registration(self):
        """Test user registration."""
        url = reverse('user-register')
        response = self.client.post(url, self.registration_data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertTrue(User.objects.filter(phone_number='01712345678').exists())
    
    def test_otp_verification(self):
        """Test OTP verification."""
        # Create user first
        user = User.objects.create_user(
            phone_number='01712345678',
            password='testpass123'
        )
        
        # Create OTP
        otp = OTPVerification.objects.create(
            phone_number='01712345678',
            otp_code='123456',
            otp_type='registration',
            expires_at=timezone.now() + timedelta(minutes=5)
        )
        
        url = reverse('verify-otp')
        data = {
            'phone_number': '01712345678',
            'otp_code': '123456',
            'otp_type': 'registration'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Check if user is activated
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_verified)
    
    def test_user_login(self):
        """Test user login."""
        user = User.objects.create_user(
            phone_number='01712345678',
            password='testpass123',
            is_active=True,
            is_verified=True
        )
        
        url = reverse('token-obtain-pair')
        data = {
            'phone_number': '01712345678',
            'password': 'testpass123'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('access_token', response.data)
        self.assertIn('refresh_token', response.data)