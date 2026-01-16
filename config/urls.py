"""
URL configuration for S-ACM project.
S-ACM - Smart Academic Content Management System
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django Admin
    path('django-admin/', admin.site.urls),
    
    # Core App (Home, Dashboard redirect)
    path('', include('core.urls')),
    
    # Accounts App (Authentication, Profile, User Management)
    path('accounts/', include('accounts.urls')),
    
    # Courses App (Courses, Files, Student/Instructor panels)
    path('courses/', include('courses.urls')),
    
    # Notifications App
    path('notifications/', include('notifications.urls')),
    
    # AI Features App
    path('ai/', include('ai_features.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
