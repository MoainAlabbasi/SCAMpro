"""
Views لتطبيق accounts
S-ACM - Smart Academic Content Management System
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db import models
from datetime import timedelta
import csv
import io

from .models import User, Role, Major, Level, Semester, VerificationCode, PasswordResetToken, UserActivity
from .forms import (
    LoginForm, ActivationStep1Form, ActivationStep2Form, OTPVerificationForm,
    SetPasswordActivationForm, PasswordResetRequestForm, ProfileUpdateForm,
    ChangePasswordForm, UserBulkImportForm, UserCreateForm, StudentPromotionForm
)
from core.models import AuditLog


# ========== Mixins ==========

class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin للتحقق من صلاحيات الأدمن"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_admin()


class InstructorRequiredMixin(UserPassesTestMixin):
    """Mixin للتحقق من صلاحيات المدرس"""
    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_instructor() or self.request.user.is_admin()
        )


class StudentRequiredMixin(UserPassesTestMixin):
    """Mixin للتحقق من صلاحيات الطالب"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_student()


# ========== Authentication Views ==========

class LoginView(View):
    """عرض تسجيل الدخول"""
    template_name = 'accounts/login.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:dashboard_redirect')
        form = LoginForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            
            # التحقق من حالة الحساب
            if user.account_status != 'active':
                messages.error(request, 'هذا الحساب غير مفعّل.')
                return render(request, self.template_name, {'form': form})
            
            login(request, user)
            
            # تسجيل النشاط
            UserActivity.objects.create(
                user=user,
                activity_type='login',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # تذكرني
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)
            
            messages.success(request, f'مرحباً {user.full_name}!')
            
            # التوجيه حسب الدور
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('core:dashboard_redirect')
        
        return render(request, self.template_name, {'form': form})
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class LogoutView(View):
    """عرض تسجيل الخروج"""
    def get(self, request):
        if request.user.is_authenticated:
            # تسجيل النشاط
            UserActivity.objects.create(
                user=request.user,
                activity_type='logout',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            logout(request)
            messages.success(request, 'تم تسجيل الخروج بنجاح.')
        return redirect('accounts:login')


# ========== Account Activation Views ==========

class ActivationStep1View(View):
    """الخطوة الأولى: التحقق من الهوية"""
    template_name = 'accounts/activation/step1.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:dashboard_redirect')
        form = ActivationStep1Form()
        return render(request, self.template_name, {'form': form, 'step': 1})
    
    def post(self, request):
        form = ActivationStep1Form(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            # حفظ معرف المستخدم في الجلسة
            request.session['activation_user_id'] = user.id
            return redirect('accounts:activation_step2')
        return render(request, self.template_name, {'form': form, 'step': 1})


class ActivationStep2View(View):
    """الخطوة الثانية: إدخال البريد الإلكتروني"""
    template_name = 'accounts/activation/step2.html'
    
    def get(self, request):
        user_id = request.session.get('activation_user_id')
        if not user_id:
            return redirect('accounts:activation_step1')
        
        form = ActivationStep2Form()
        return render(request, self.template_name, {'form': form, 'step': 2})
    
    def post(self, request):
        user_id = request.session.get('activation_user_id')
        if not user_id:
            return redirect('accounts:activation_step1')
        
        form = ActivationStep2Form(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = get_object_or_404(User, id=user_id)
            
            # إنشاء رمز OTP
            otp_code = VerificationCode.generate_code()
            VerificationCode.objects.create(
                user=user,
                code=otp_code,
                email=email,
                expires_at=timezone.now() + timedelta(minutes=10)
            )
            
            # إرسال البريد الإلكتروني
            try:
                send_mail(
                    subject='رمز تفعيل حسابك في S-ACM',
                    message=f'رمز التفعيل الخاص بك هو: {otp_code}\n\nهذا الرمز صالح لمدة 10 دقائق.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as e:
                # في حالة فشل الإرسال، نعرض الرمز للتطوير
                messages.info(request, f'رمز التحقق (للتطوير): {otp_code}')
            
            request.session['activation_email'] = email
            messages.success(request, 'تم إرسال رمز التحقق إلى بريدك الإلكتروني.')
            return redirect('accounts:activation_verify_otp')
        
        return render(request, self.template_name, {'form': form, 'step': 2})


class ActivationVerifyOTPView(View):
    """الخطوة الثالثة: التحقق من رمز OTP"""
    template_name = 'accounts/activation/verify_otp.html'
    
    def get(self, request):
        user_id = request.session.get('activation_user_id')
        email = request.session.get('activation_email')
        if not user_id or not email:
            return redirect('accounts:activation_step1')
        
        form = OTPVerificationForm()
        return render(request, self.template_name, {
            'form': form,
            'step': 3,
            'email': email
        })
    
    def post(self, request):
        user_id = request.session.get('activation_user_id')
        email = request.session.get('activation_email')
        if not user_id or not email:
            return redirect('accounts:activation_step1')
        
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            otp_code = form.cleaned_data['otp_code']
            user = get_object_or_404(User, id=user_id)
            
            # التحقق من الرمز
            verification = VerificationCode.objects.filter(
                user=user,
                email=email,
                code=otp_code,
                is_used=False
            ).first()
            
            if verification and verification.is_valid():
                verification.is_used = True
                verification.save()
                request.session['otp_verified'] = True
                return redirect('accounts:activation_set_password')
            else:
                # زيادة عدد المحاولات
                if verification:
                    verification.attempts += 1
                    verification.save()
                messages.error(request, 'رمز التحقق غير صحيح أو منتهي الصلاحية.')
        
        return render(request, self.template_name, {
            'form': form,
            'step': 3,
            'email': email
        })


class ActivationSetPasswordView(View):
    """الخطوة الرابعة: تعيين كلمة المرور"""
    template_name = 'accounts/activation/set_password.html'
    
    def get(self, request):
        user_id = request.session.get('activation_user_id')
        otp_verified = request.session.get('otp_verified')
        if not user_id or not otp_verified:
            return redirect('accounts:activation_step1')
        
        user = get_object_or_404(User, id=user_id)
        form = SetPasswordActivationForm(user)
        return render(request, self.template_name, {'form': form, 'step': 4})
    
    def post(self, request):
        user_id = request.session.get('activation_user_id')
        otp_verified = request.session.get('otp_verified')
        if not user_id or not otp_verified:
            return redirect('accounts:activation_step1')
        
        user = get_object_or_404(User, id=user_id)
        form = SetPasswordActivationForm(user, request.POST)
        
        if form.is_valid():
            # تحديث المستخدم
            email = request.session.get('activation_email')
            user.email = email
            user.account_status = 'active'
            user.set_password(form.cleaned_data['new_password1'])
            user.save()
            
            # تنظيف الجلسة
            for key in ['activation_user_id', 'activation_email', 'otp_verified']:
                request.session.pop(key, None)
            
            # تسجيل في سجل التدقيق
            AuditLog.log(
                user=user,
                action='create',
                model_name='User',
                object_id=user.id,
                object_repr=str(user),
                changes={'action': 'account_activated'},
                request=request
            )
            
            messages.success(request, 'تم تفعيل حسابك بنجاح! يمكنك الآن تسجيل الدخول.')
            return redirect('accounts:login')
        
        return render(request, self.template_name, {'form': form, 'step': 4})


# ========== Password Reset Views ==========

class PasswordResetRequestView(View):
    """طلب إعادة تعيين كلمة المرور"""
    template_name = 'accounts/password_reset/request.html'
    
    def get(self, request):
        form = PasswordResetRequestForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            user = form.user
            
            # إنشاء توكن
            token = PasswordResetToken.generate_token()
            PasswordResetToken.objects.create(
                user=user,
                token=token,
                expires_at=timezone.now() + timedelta(hours=1)
            )
            
            # إرسال البريد
            reset_url = request.build_absolute_uri(
                reverse('accounts:password_reset_confirm', args=[token])
            )
            
            try:
                send_mail(
                    subject='إعادة تعيين كلمة المرور - S-ACM',
                    message=f'لإعادة تعيين كلمة المرور، اضغط على الرابط التالي:\n\n{reset_url}\n\nهذا الرابط صالح لمدة ساعة واحدة.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                messages.success(request, 'تم إرسال رابط إعادة التعيين إلى بريدك الإلكتروني.')
            except Exception as e:
                messages.info(request, f'رابط إعادة التعيين (للتطوير): {reset_url}')
            
            return redirect('accounts:login')
        
        return render(request, self.template_name, {'form': form})


class PasswordResetConfirmView(View):
    """تأكيد إعادة تعيين كلمة المرور"""
    template_name = 'accounts/password_reset/confirm.html'
    
    def get(self, request, token):
        reset_token = get_object_or_404(PasswordResetToken, token=token)
        
        if not reset_token.is_valid():
            messages.error(request, 'رابط إعادة التعيين غير صالح أو منتهي الصلاحية.')
            return redirect('accounts:password_reset_request')
        
        form = SetPasswordActivationForm(reset_token.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request, token):
        reset_token = get_object_or_404(PasswordResetToken, token=token)
        
        if not reset_token.is_valid():
            messages.error(request, 'رابط إعادة التعيين غير صالح أو منتهي الصلاحية.')
            return redirect('accounts:password_reset_request')
        
        form = SetPasswordActivationForm(reset_token.user, request.POST)
        if form.is_valid():
            user = reset_token.user
            user.set_password(form.cleaned_data['new_password1'])
            user.save()
            
            reset_token.is_used = True
            reset_token.save()
            
            messages.success(request, 'تم تغيير كلمة المرور بنجاح!')
            return redirect('accounts:login')
        
        return render(request, self.template_name, {'form': form})


# ========== Profile Views ==========

class ProfileView(LoginRequiredMixin, TemplateView):
    """عرض الملف الشخصي"""
    template_name = 'accounts/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['recent_activities'] = UserActivity.objects.filter(
            user=self.request.user
        )[:10]
        return context


class ProfileUpdateView(LoginRequiredMixin, View):
    """تحديث الملف الشخصي"""
    template_name = 'accounts/profile_update.html'
    
    def get(self, request):
        form = ProfileUpdateForm(instance=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_update',
                description='تم تحديث الملف الشخصي',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, 'تم تحديث الملف الشخصي بنجاح.')
            return redirect('accounts:profile')
        
        return render(request, self.template_name, {'form': form})


class ChangePasswordView(LoginRequiredMixin, View):
    """تغيير كلمة المرور"""
    template_name = 'accounts/change_password.html'
    
    def get(self, request):
        form = ChangePasswordForm(request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password1'])
            request.user.save()
            
            # الحفاظ على الجلسة
            update_session_auth_hash(request, request.user)
            
            UserActivity.objects.create(
                user=request.user,
                activity_type='password_change',
                description='تم تغيير كلمة المرور',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, 'تم تغيير كلمة المرور بنجاح.')
            return redirect('accounts:profile')
        
        return render(request, self.template_name, {'form': form})


# ========== Admin Views ==========

class AdminDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """لوحة تحكم الأدمن"""
    template_name = 'admin_panel/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(account_status='active').count()
        context['total_students'] = User.objects.filter(role__role_name='Student').count()
        context['total_instructors'] = User.objects.filter(role__role_name='Instructor').count()
        context['total_majors'] = Major.objects.filter(is_active=True).count()
        context['current_semester'] = Semester.objects.filter(is_current=True).first()
        context['recent_activities'] = UserActivity.objects.all()[:20]
        return context


class UserListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """قائمة المستخدمين"""
    model = User
    template_name = 'admin_panel/users/list.html'
    context_object_name = 'users'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = User.objects.select_related('role', 'major', 'level')
        
        # فلترة
        role = self.request.GET.get('role')
        major = self.request.GET.get('major')
        level = self.request.GET.get('level')
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')
        
        if role:
            queryset = queryset.filter(role_id=role)
        if major:
            queryset = queryset.filter(major_id=major)
        if level:
            queryset = queryset.filter(level_id=level)
        if status:
            queryset = queryset.filter(account_status=status)
        if search:
            queryset = queryset.filter(
                models.Q(academic_id__icontains=search) |
                models.Q(full_name__icontains=search) |
                models.Q(email__icontains=search)
            )
        
        return queryset.order_by('-date_joined')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['roles'] = Role.objects.all()
        context['majors'] = Major.objects.filter(is_active=True)
        context['levels'] = Level.objects.all()
        return context


class UserCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """إنشاء مستخدم جديد"""
    model = User
    form_class = UserCreateForm
    template_name = 'admin_panel/users/create.html'
    success_url = reverse_lazy('accounts:admin_user_list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        AuditLog.log(
            user=self.request.user,
            action='create',
            model_name='User',
            object_id=self.object.id,
            object_repr=str(self.object),
            request=self.request
        )
        
        messages.success(self.request, f'تم إنشاء المستخدم {self.object.full_name} بنجاح.')
        return response


class UserBulkImportView(LoginRequiredMixin, AdminRequiredMixin, View):
    """استيراد المستخدمين بالجملة"""
    template_name = 'admin_panel/users/bulk_import.html'
    
    def get(self, request):
        form = UserBulkImportForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = UserBulkImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['csv_file']
            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded_file))
            
            created_count = 0
            errors = []
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    role = Role.objects.get(role_name=row.get('role', 'Student'))
                    major = None
                    level = None
                    
                    if row.get('major'):
                        major = Major.objects.get(major_name=row['major'])
                    if row.get('level'):
                        level = Level.objects.get(level_name=row['level'])
                    
                    User.objects.create(
                        academic_id=row['academic_id'],
                        id_card_number=row['id_card_number'],
                        full_name=row['full_name'],
                        role=role,
                        major=major,
                        level=level
                    )
                    created_count += 1
                except Exception as e:
                    errors.append(f'خطأ في السطر {row_num}: {str(e)}')
            
            if created_count > 0:
                messages.success(request, f'تم استيراد {created_count} مستخدم بنجاح.')
            if errors:
                for error in errors[:5]:  # عرض أول 5 أخطاء فقط
                    messages.warning(request, error)
            
            return redirect('accounts:admin_user_list')
        
        return render(request, self.template_name, {'form': form})


class StudentPromotionView(LoginRequiredMixin, AdminRequiredMixin, View):
    """ترقية الطلاب الجماعية"""
    template_name = 'admin_panel/users/promotion.html'
    
    def get(self, request):
        form = StudentPromotionForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = StudentPromotionForm(request.POST)
        if form.is_valid():
            from_level = form.cleaned_data['from_level']
            to_level = form.cleaned_data['to_level']
            major = form.cleaned_data.get('major')
            
            # بناء الاستعلام
            students = User.objects.filter(
                role__role_name='Student',
                level=from_level,
                account_status='active'
            )
            
            if major:
                students = students.filter(major=major)
            
            # تنفيذ الترقية
            count = students.update(level=to_level)
            
            # تسجيل في سجل التدقيق
            AuditLog.log(
                user=request.user,
                action='promote',
                model_name='User',
                changes={
                    'from_level': str(from_level),
                    'to_level': str(to_level),
                    'major': str(major) if major else 'all',
                    'count': count
                },
                request=request
            )
            
            messages.success(request, f'تم ترقية {count} طالب من {from_level} إلى {to_level}.')
            return redirect('accounts:admin_user_list')
        
        return render(request, self.template_name, {'form': form})
