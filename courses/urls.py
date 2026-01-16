"""
URLs لتطبيق courses
S-ACM - Smart Academic Content Management System
"""

from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    # Student URLs
    path('student/', views.StudentDashboardView.as_view(), name='student_dashboard'),
    path('student/courses/', views.StudentCourseListView.as_view(), name='student_course_list'),
    path('student/courses/<int:pk>/', views.StudentCourseDetailView.as_view(), name='student_course_detail'),
    
    # File Operations
    path('files/<int:pk>/download/', views.FileDownloadView.as_view(), name='file_download'),
    path('files/<int:pk>/view/', views.FileViewView.as_view(), name='file_view'),
    
    # Instructor URLs
    path('instructor/', views.InstructorDashboardView.as_view(), name='instructor_dashboard'),
    path('instructor/courses/', views.InstructorCourseListView.as_view(), name='instructor_course_list'),
    path('instructor/courses/<int:pk>/', views.InstructorCourseDetailView.as_view(), name='instructor_course_detail'),
    path('instructor/files/upload/', views.FileUploadView.as_view(), name='file_upload'),
    path('instructor/files/<int:pk>/update/', views.FileUpdateView.as_view(), name='file_update'),
    path('instructor/files/<int:pk>/delete/', views.FileDeleteView.as_view(), name='file_delete'),
    path('instructor/files/<int:pk>/toggle-visibility/', views.FileToggleVisibilityView.as_view(), name='file_toggle_visibility'),
    
    # Admin URLs
    path('admin/courses/', views.AdminCourseListView.as_view(), name='admin_course_list'),
    path('admin/courses/create/', views.AdminCourseCreateView.as_view(), name='admin_course_create'),
    path('admin/courses/<int:pk>/update/', views.AdminCourseUpdateView.as_view(), name='admin_course_update'),
    path('admin/courses/<int:pk>/assign-instructor/', views.AdminInstructorAssignView.as_view(), name='admin_instructor_assign'),
]
