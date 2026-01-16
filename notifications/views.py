"""
Views لتطبيق notifications
S-ACM - Smart Academic Content Management System
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, CreateView
from django.http import JsonResponse
from django.urls import reverse_lazy

from .models import Notification, NotificationRecipient, NotificationManager
from .forms import NotificationForm, CourseNotificationForm
from accounts.views import InstructorRequiredMixin, AdminRequiredMixin
from courses.models import Course


class NotificationListView(LoginRequiredMixin, ListView):
    """قائمة إشعارات المستخدم"""
    template_name = 'notifications/list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return NotificationManager.get_user_notifications(
            self.request.user,
            include_read=True
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_count'] = NotificationManager.get_unread_count(self.request.user)
        return context


class NotificationDetailView(LoginRequiredMixin, View):
    """عرض تفاصيل الإشعار"""
    template_name = 'notifications/detail.html'
    
    def get(self, request, pk):
        recipient = get_object_or_404(
            NotificationRecipient,
            notification_id=pk,
            user=request.user,
            is_deleted=False
        )
        
        # تحديد كمقروء
        recipient.mark_as_read()
        
        return render(request, self.template_name, {
            'notification': recipient.notification,
            'recipient': recipient
        })


class MarkAsReadView(LoginRequiredMixin, View):
    """تحديد إشعار كمقروء"""
    
    def post(self, request, pk):
        recipient = get_object_or_404(
            NotificationRecipient,
            notification_id=pk,
            user=request.user
        )
        recipient.mark_as_read()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        return redirect('notifications:list')


class MarkAllAsReadView(LoginRequiredMixin, View):
    """تحديد جميع الإشعارات كمقروءة"""
    
    def post(self, request):
        from django.utils import timezone
        
        NotificationRecipient.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        messages.success(request, 'تم تحديد جميع الإشعارات كمقروءة.')
        return redirect('notifications:list')


class DeleteNotificationView(LoginRequiredMixin, View):
    """حذف إشعار من قائمة المستخدم"""
    
    def post(self, request, pk):
        recipient = get_object_or_404(
            NotificationRecipient,
            notification_id=pk,
            user=request.user
        )
        recipient.is_deleted = True
        recipient.save(update_fields=['is_deleted'])
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        messages.success(request, 'تم حذف الإشعار.')
        return redirect('notifications:list')


class UnreadCountView(LoginRequiredMixin, View):
    """الحصول على عدد الإشعارات غير المقروءة (AJAX)"""
    
    def get(self, request):
        count = NotificationManager.get_unread_count(request.user)
        return JsonResponse({'count': count})


# ========== Instructor Notification Views ==========

class InstructorNotificationCreateView(LoginRequiredMixin, InstructorRequiredMixin, CreateView):
    """إنشاء إشعار للمقرر (للمدرس)"""
    model = Notification
    form_class = CourseNotificationForm
    template_name = 'instructor_panel/notifications/create.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        course = form.cleaned_data['course']
        title = form.cleaned_data['title']
        body = form.cleaned_data['body']
        
        notification = NotificationManager.create_course_notification(
            sender=self.request.user,
            course=course,
            title=title,
            body=body
        )
        
        messages.success(self.request, 'تم إرسال الإشعار بنجاح.')
        return redirect('courses:instructor_course_detail', pk=course.pk)


class InstructorNotificationListView(LoginRequiredMixin, InstructorRequiredMixin, ListView):
    """قائمة الإشعارات المرسلة (للمدرس)"""
    template_name = 'instructor_panel/notifications/list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return Notification.objects.filter(
            sender=self.request.user
        ).order_by('-created_at')


# ========== Admin Notification Views ==========

class AdminNotificationCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """إنشاء إشعار عام (للأدمن)"""
    model = Notification
    form_class = NotificationForm
    template_name = 'admin_panel/notifications/create.html'
    success_url = reverse_lazy('notifications:admin_list')
    
    def form_valid(self, form):
        notification = form.save(commit=False)
        notification.sender = self.request.user
        notification.save()
        
        # تحديد المستلمين
        target = form.cleaned_data.get('target')
        
        from accounts.models import User
        
        if target == 'all':
            users = User.objects.filter(account_status='active')
        elif target == 'students':
            users = User.objects.filter(role__role_name='Student', account_status='active')
        elif target == 'instructors':
            users = User.objects.filter(role__role_name='Instructor', account_status='active')
        else:
            users = User.objects.filter(account_status='active')
        
        # إنشاء سجلات المستلمين
        recipients = [
            NotificationRecipient(notification=notification, user=user)
            for user in users
        ]
        NotificationRecipient.objects.bulk_create(recipients)
        
        messages.success(self.request, f'تم إرسال الإشعار إلى {len(recipients)} مستخدم.')
        return redirect(self.success_url)


class AdminNotificationListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """قائمة جميع الإشعارات (للأدمن)"""
    model = Notification
    template_name = 'admin_panel/notifications/list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return Notification.objects.all().order_by('-created_at')
