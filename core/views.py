"""
Views لتطبيق core
S-ACM - Smart Academic Content Management System
"""

from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


class HomeView(TemplateView):
    """الصفحة الرئيسية"""
    template_name = 'core/home.html'
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('core:dashboard_redirect')
        return super().get(request, *args, **kwargs)


@login_required
def dashboard_redirect(request):
    """
    توجيه المستخدم إلى لوحة التحكم المناسبة حسب دوره
    """
    user = request.user
    
    if user.is_admin():
        return redirect('accounts:admin_dashboard')
    elif user.is_instructor():
        return redirect('courses:instructor_dashboard')
    elif user.is_student():
        return redirect('courses:student_dashboard')
    else:
        # إذا لم يكن له دور محدد
        return redirect('accounts:profile')


class AboutView(TemplateView):
    """صفحة عن النظام"""
    template_name = 'core/about.html'


class ContactView(TemplateView):
    """صفحة التواصل"""
    template_name = 'core/contact.html'


class Error404View(TemplateView):
    """صفحة خطأ 404"""
    template_name = 'errors/404.html'


class Error500View(TemplateView):
    """صفحة خطأ 500"""
    template_name = 'errors/500.html'
