"""
خدمات إدارة المحتوى والملفات
S-ACM - Smart Academic Content Management System
"""

import os
from pathlib import Path
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.text import slugify
from datetime import datetime


class FileService:
    """خدمة إدارة الملفات"""
    
    ALLOWED_EXTENSIONS = {
        'document': ['.pdf', '.doc', '.docx', '.txt', '.md'],
        'presentation': ['.ppt', '.pptx'],
        'video': ['.mp4', '.webm', '.avi', '.mov'],
        'image': ['.jpg', '.jpeg', '.png', '.gif'],
        'other': ['.zip', '.rar']
    }
    
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    
    @classmethod
    def get_upload_path(cls, instance, filename):
        """
        توليد مسار رفع الملف
        Format: uploads/courses/{course_code}/{semester}/{filename}
        """
        # الحصول على امتداد الملف
        ext = Path(filename).suffix.lower()
        
        # توليد اسم فريد للملف
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = slugify(Path(filename).stem, allow_unicode=True)
        new_filename = f"{safe_name}_{timestamp}{ext}"
        
        # بناء المسار
        course_code = instance.course.course_code if instance.course else 'unknown'
        semester = instance.semester.semester_name if instance.semester else 'general'
        
        return os.path.join('uploads', 'courses', course_code, semester, new_filename)
    
    @classmethod
    def validate_file(cls, file):
        """
        التحقق من صحة الملف
        Returns: (is_valid, error_message)
        """
        if not file:
            return False, "لم يتم اختيار ملف"
        
        # التحقق من الحجم
        if file.size > cls.MAX_FILE_SIZE:
            max_mb = cls.MAX_FILE_SIZE / (1024 * 1024)
            return False, f"حجم الملف يتجاوز الحد المسموح ({max_mb} ميجابايت)"
        
        # التحقق من الامتداد
        ext = Path(file.name).suffix.lower()
        all_allowed = []
        for exts in cls.ALLOWED_EXTENSIONS.values():
            all_allowed.extend(exts)
        
        if ext not in all_allowed:
            return False, f"نوع الملف غير مدعوم. الأنواع المدعومة: {', '.join(all_allowed)}"
        
        return True, None
    
    @classmethod
    def get_file_type(cls, filename):
        """تحديد نوع الملف"""
        ext = Path(filename).suffix.lower()
        
        for file_type, extensions in cls.ALLOWED_EXTENSIONS.items():
            if ext in extensions:
                return file_type
        
        return 'other'
    
    @classmethod
    def delete_file(cls, file_path):
        """حذف ملف من التخزين"""
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
                return True
        except Exception as e:
            print(f"Error deleting file: {e}")
        return False
    
    @classmethod
    def get_file_size_display(cls, size_bytes):
        """عرض حجم الملف بشكل مقروء"""
        if size_bytes < 1024:
            return f"{size_bytes} بايت"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} كيلوبايت"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} ميجابايت"


class NotificationService:
    """خدمة الإشعارات"""
    
    @classmethod
    def notify_new_file(cls, file_obj):
        """
        إرسال إشعار عند رفع ملف جديد
        """
        from notifications.models import Notification
        from accounts.models import User
        
        course = file_obj.course
        
        # الحصول على جميع الطلاب المسجلين في التخصصات المرتبطة بالمقرر
        majors = course.course_majors.values_list('major_id', flat=True)
        students = User.objects.filter(
            role__role_name='student',
            major_id__in=majors,
            level=course.level,
            account_status='active'
        )
        
        # إنشاء إشعار لكل طالب
        notifications = []
        for student in students:
            notifications.append(Notification(
                user=student,
                title=f"ملف جديد في {course.course_name}",
                body=f"تم رفع ملف جديد: {file_obj.title}",
                notification_type='new_file',
                related_course=course
            ))
        
        if notifications:
            Notification.objects.bulk_create(notifications)
        
        return len(notifications)
    
    @classmethod
    def notify_announcement(cls, title, body, course=None, target_role=None):
        """
        إرسال إعلان عام
        """
        from notifications.models import Notification
        from accounts.models import User
        
        users = User.objects.filter(account_status='active')
        
        if target_role:
            users = users.filter(role__role_name=target_role)
        
        if course:
            majors = course.course_majors.values_list('major_id', flat=True)
            users = users.filter(major_id__in=majors, level=course.level)
        
        notifications = []
        for user in users:
            notifications.append(Notification(
                user=user,
                title=title,
                body=body,
                notification_type='info',
                related_course=course
            ))
        
        if notifications:
            Notification.objects.bulk_create(notifications)
        
        return len(notifications)


class ArchiveService:
    """خدمة الأرشفة الذكية"""
    
    @classmethod
    def is_archived_for_student(cls, course, student):
        """
        التحقق مما إذا كان المقرر مؤرشفاً بالنسبة للطالب
        
        المنطق:
        - إذا كان الفصل الدراسي غير حالي (is_current = False)
        - و مستوى الطالب أعلى من مستوى المقرر
        - فإن المقرر يعتبر مؤرشفاً
        """
        from accounts.models import Semester
        
        # الحصول على الفصل الحالي
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return False
        
        # التحقق من مستوى الطالب مقارنة بمستوى المقرر
        if student.level and course.level:
            student_level_number = student.level.level_number
            course_level_number = course.level.level_number
            
            if student_level_number > course_level_number:
                return True
        
        return False
    
    @classmethod
    def get_student_courses(cls, student, archived=False):
        """
        الحصول على مقررات الطالب (الحالية أو المؤرشفة)
        """
        from courses.models import Course
        
        # الحصول على المقررات المرتبطة بتخصص الطالب
        courses = Course.objects.filter(
            course_majors__major=student.major,
            is_active=True
        ).distinct()
        
        result = []
        for course in courses:
            is_archived = cls.is_archived_for_student(course, student)
            
            if archived and is_archived:
                result.append(course)
            elif not archived and not is_archived:
                # فقط المقررات التي تطابق مستوى الطالب
                if course.level == student.level:
                    result.append(course)
        
        return result


class PromotionService:
    """خدمة ترقية الطلاب"""
    
    @classmethod
    def promote_students(cls, from_level):
        """
        ترقية جميع طلاب مستوى معين إلى المستوى التالي
        """
        from accounts.models import User, Level
        
        # الحصول على المستوى التالي
        try:
            next_level = Level.objects.get(level_number=from_level.level_number + 1)
        except Level.DoesNotExist:
            return 0, "لا يوجد مستوى تالي"
        
        # ترقية الطلاب
        students = User.objects.filter(
            role__role_name='student',
            level=from_level,
            account_status='active'
        )
        
        count = students.update(level=next_level)
        
        return count, None
    
    @classmethod
    def get_promotion_stats(cls):
        """
        الحصول على إحصائيات الترقية
        """
        from accounts.models import User, Level
        
        levels = Level.objects.all().order_by('level_number')
        stats = []
        
        for level in levels:
            student_count = User.objects.filter(
                role__role_name='student',
                level=level,
                account_status='active'
            ).count()
            
            try:
                next_level = Level.objects.get(level_number=level.level_number + 1)
            except Level.DoesNotExist:
                next_level = None
            
            stats.append({
                'level': level,
                'student_count': student_count,
                'next_level': next_level
            })
        
        return stats
