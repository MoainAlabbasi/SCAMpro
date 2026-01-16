"""
Context Processors للمتغيرات العامة في القوالب
S-ACM - Smart Academic Content Management System
"""

from django.conf import settings


def site_settings(request):
    """
    إضافة إعدادات الموقع للقوالب
    """
    return {
        'SITE_NAME': 'S-ACM',
        'SITE_FULL_NAME': 'نظام إدارة المحتوى الأكاديمي الذكي',
        'SITE_VERSION': '1.0.0',
        'DEBUG': settings.DEBUG,
    }


def user_notifications(request):
    """
    إضافة عدد الإشعارات غير المقروءة
    """
    if request.user.is_authenticated:
        from notifications.models import Notification
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        return {
            'unread_notifications_count': unread_count
        }
    return {
        'unread_notifications_count': 0
    }


def user_role_info(request):
    """
    إضافة معلومات دور المستخدم
    """
    if request.user.is_authenticated:
        role = request.user.role
        return {
            'user_role': role.role_name if role else None,
            'is_admin': role and role.role_name == 'admin',
            'is_instructor': role and role.role_name == 'instructor',
            'is_student': role and role.role_name == 'student',
        }
    return {
        'user_role': None,
        'is_admin': False,
        'is_instructor': False,
        'is_student': False,
    }


def current_semester(request):
    """
    إضافة الفصل الدراسي الحالي
    """
    from accounts.models import Semester
    
    try:
        semester = Semester.objects.filter(is_current=True).first()
        return {
            'current_semester': semester
        }
    except:
        return {
            'current_semester': None
        }
