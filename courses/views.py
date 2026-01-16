"""
Views لتطبيق courses
S-ACM - Smart Academic Content Management System
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponse, FileResponse
from django.db.models import Q, Count
from django.utils import timezone
from django.conf import settings
from pathlib import Path
import mimetypes

from .models import Course, CourseMajor, InstructorCourse, LectureFile
from .forms import CourseForm, LectureFileForm, CourseMajorFormSet
from accounts.models import User, UserActivity, Major, Level, Semester
from accounts.views import AdminRequiredMixin, InstructorRequiredMixin, StudentRequiredMixin
from notifications.models import NotificationManager
from core.models import AuditLog


# ========== Student Views ==========

class StudentDashboardView(LoginRequiredMixin, StudentRequiredMixin, TemplateView):
    """لوحة تحكم الطالب"""
    template_name = 'student_panel/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.request.user
        
        # المقررات الحالية
        context['current_courses'] = Course.objects.get_current_courses_for_student(student)
        
        # المقررات المؤرشفة
        context['archived_courses'] = Course.objects.get_archived_courses_for_student(student)
        
        # الإشعارات غير المقروءة
        from notifications.models import NotificationManager
        context['unread_notifications'] = NotificationManager.get_unread_count(student)
        
        # آخر الملفات المرفوعة
        context['recent_files'] = LectureFile.objects.filter(
            course__in=context['current_courses'],
            is_visible=True,
            is_deleted=False
        ).order_by('-upload_date')[:5]
        
        return context


class StudentCourseListView(LoginRequiredMixin, StudentRequiredMixin, ListView):
    """قائمة مقررات الطالب"""
    template_name = 'student_panel/courses/list.html'
    context_object_name = 'courses'
    
    def get_queryset(self):
        student = self.request.user
        view_type = self.request.GET.get('view', 'current')
        
        if view_type == 'archived':
            return Course.objects.get_archived_courses_for_student(student)
        return Course.objects.get_current_courses_for_student(student)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['view_type'] = self.request.GET.get('view', 'current')
        return context


class StudentCourseDetailView(LoginRequiredMixin, StudentRequiredMixin, DetailView):
    """تفاصيل المقرر للطالب"""
    model = Course
    template_name = 'student_panel/courses/detail.html'
    context_object_name = 'course'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.object
        
        # الملفات حسب النوع
        files = course.files.filter(is_visible=True, is_deleted=False)
        context['lectures'] = files.filter(file_type='Lecture')
        context['summaries'] = files.filter(file_type='Summary')
        context['exams'] = files.filter(file_type='Exam')
        context['assignments'] = files.filter(file_type='Assignment')
        context['references'] = files.filter(file_type='Reference')
        context['others'] = files.filter(file_type='Other')
        
        # المدرسين
        context['instructors'] = course.instructor_courses.select_related('instructor')
        
        return context


class FileDownloadView(LoginRequiredMixin, View):
    """تحميل الملفات"""
    
    def get(self, request, pk):
        file_obj = get_object_or_404(LectureFile, pk=pk, is_deleted=False)
        
        # التحقق من الصلاحية
        user = request.user
        if user.is_student():
            # التحقق من أن الطالب مسجل في المقرر
            if not file_obj.is_visible:
                messages.error(request, 'هذا الملف غير متاح حالياً.')
                return redirect('courses:student_course_detail', pk=file_obj.course.pk)
        
        # زيادة عداد التحميل
        file_obj.increment_download()
        
        # تسجيل النشاط
        UserActivity.objects.create(
            user=user,
            activity_type='download',
            description=f'تحميل ملف: {file_obj.title}',
            file_id=file_obj.id,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # إذا كان رابط خارجي
        if file_obj.content_type == 'external_link':
            return redirect(file_obj.external_link)
        
        # إذا كان ملف محلي
        if file_obj.local_file:
            file_path = file_obj.local_file.path
            content_type, _ = mimetypes.guess_type(file_path)
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=content_type or 'application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{Path(file_path).name}"'
            return response
        
        messages.error(request, 'الملف غير موجود.')
        return redirect('courses:student_dashboard')


class FileViewView(LoginRequiredMixin, View):
    """عرض الملفات (للـ PDF والفيديو)"""
    
    def get(self, request, pk):
        file_obj = get_object_or_404(LectureFile, pk=pk, is_deleted=False)
        
        # زيادة عداد المشاهدة
        file_obj.increment_view()
        
        # تسجيل النشاط
        UserActivity.objects.create(
            user=request.user,
            activity_type='view',
            description=f'عرض ملف: {file_obj.title}',
            file_id=file_obj.id,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        context = {
            'file': file_obj,
            'course': file_obj.course
        }
        
        return render(request, 'courses/file_viewer.html', context)


# ========== Instructor Views ==========

class InstructorDashboardView(LoginRequiredMixin, InstructorRequiredMixin, TemplateView):
    """لوحة تحكم المدرس"""
    template_name = 'instructor_panel/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instructor = self.request.user
        
        # المقررات المعينة
        context['my_courses'] = Course.objects.get_courses_for_instructor(instructor)
        
        # إحصائيات
        context['total_files'] = LectureFile.objects.filter(
            uploader=instructor,
            is_deleted=False
        ).count()
        
        context['total_downloads'] = LectureFile.objects.filter(
            uploader=instructor,
            is_deleted=False
        ).aggregate(total=Count('download_count'))['total'] or 0
        
        # آخر الملفات المرفوعة
        context['recent_uploads'] = LectureFile.objects.filter(
            uploader=instructor,
            is_deleted=False
        ).order_by('-upload_date')[:5]
        
        return context


class InstructorCourseListView(LoginRequiredMixin, InstructorRequiredMixin, ListView):
    """قائمة مقررات المدرس"""
    template_name = 'instructor_panel/courses/list.html'
    context_object_name = 'courses'
    
    def get_queryset(self):
        return Course.objects.get_courses_for_instructor(self.request.user)


class InstructorCourseDetailView(LoginRequiredMixin, InstructorRequiredMixin, DetailView):
    """تفاصيل المقرر للمدرس"""
    model = Course
    template_name = 'instructor_panel/courses/detail.html'
    context_object_name = 'course'
    
    def get_queryset(self):
        return Course.objects.get_courses_for_instructor(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.object
        
        # جميع الملفات (بما فيها المخفية)
        files = course.files.filter(is_deleted=False)
        context['all_files'] = files
        context['visible_files'] = files.filter(is_visible=True)
        context['hidden_files'] = files.filter(is_visible=False)
        
        # إحصائيات
        context['total_downloads'] = sum(f.download_count for f in files)
        context['total_views'] = sum(f.view_count for f in files)
        
        # عدد الطلاب
        context['students_count'] = User.objects.filter(
            role__role_name='Student',
            major__in=course.course_majors.values_list('major', flat=True),
            level=course.level,
            account_status='active'
        ).count()
        
        return context


class FileUploadView(LoginRequiredMixin, InstructorRequiredMixin, CreateView):
    """رفع ملف جديد"""
    model = LectureFile
    form_class = LectureFileForm
    template_name = 'instructor_panel/files/upload.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course_id = self.request.GET.get('course')
        if course_id:
            context['selected_course'] = get_object_or_404(Course, pk=course_id)
        return context
    
    def form_valid(self, form):
        form.instance.uploader = self.request.user
        response = super().form_valid(form)
        
        # تسجيل النشاط
        UserActivity.objects.create(
            user=self.request.user,
            activity_type='upload',
            description=f'رفع ملف: {self.object.title}',
            file_id=self.object.id,
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
        
        # إرسال إشعار للطلاب
        if self.object.is_visible:
            NotificationManager.create_file_upload_notification(
                self.object,
                self.object.course
            )
        
        messages.success(self.request, f'تم رفع الملف "{self.object.title}" بنجاح.')
        return response
    
    def get_success_url(self):
        return reverse('courses:instructor_course_detail', kwargs={'pk': self.object.course.pk})


class FileUpdateView(LoginRequiredMixin, InstructorRequiredMixin, UpdateView):
    """تحديث ملف"""
    model = LectureFile
    form_class = LectureFileForm
    template_name = 'instructor_panel/files/update.html'
    
    def get_queryset(self):
        return LectureFile.objects.filter(uploader=self.request.user, is_deleted=False)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'تم تحديث الملف "{self.object.title}" بنجاح.')
        return response
    
    def get_success_url(self):
        return reverse('courses:instructor_course_detail', kwargs={'pk': self.object.course.pk})


class FileDeleteView(LoginRequiredMixin, InstructorRequiredMixin, View):
    """حذف ملف (حذف ناعم)"""
    
    def post(self, request, pk):
        file_obj = get_object_or_404(
            LectureFile,
            pk=pk,
            uploader=request.user,
            is_deleted=False
        )
        
        file_obj.soft_delete()
        
        messages.success(request, f'تم حذف الملف "{file_obj.title}".')
        return redirect('courses:instructor_course_detail', pk=file_obj.course.pk)


class FileToggleVisibilityView(LoginRequiredMixin, InstructorRequiredMixin, View):
    """تبديل ظهور الملف"""
    
    def post(self, request, pk):
        file_obj = get_object_or_404(
            LectureFile,
            pk=pk,
            uploader=request.user,
            is_deleted=False
        )
        
        file_obj.is_visible = not file_obj.is_visible
        file_obj.save(update_fields=['is_visible'])
        
        status = 'مرئي' if file_obj.is_visible else 'مخفي'
        messages.success(request, f'تم تغيير حالة الملف إلى {status}.')
        
        # إرسال إشعار إذا أصبح مرئياً
        if file_obj.is_visible:
            NotificationManager.create_file_upload_notification(
                file_obj,
                file_obj.course
            )
        
        return redirect('courses:instructor_course_detail', pk=file_obj.course.pk)


# ========== Admin Course Views ==========

class AdminCourseListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """قائمة المقررات للأدمن"""
    model = Course
    template_name = 'admin_panel/courses/list.html'
    context_object_name = 'courses'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Course.objects.select_related('level', 'semester')
        
        # فلترة
        level = self.request.GET.get('level')
        semester = self.request.GET.get('semester')
        search = self.request.GET.get('search')
        
        if level:
            queryset = queryset.filter(level_id=level)
        if semester:
            queryset = queryset.filter(semester_id=semester)
        if search:
            queryset = queryset.filter(
                Q(course_code__icontains=search) |
                Q(course_name__icontains=search)
            )
        
        return queryset.order_by('course_code')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['levels'] = Level.objects.all()
        context['semesters'] = Semester.objects.all()
        return context


class AdminCourseCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """إنشاء مقرر جديد"""
    model = Course
    form_class = CourseForm
    template_name = 'admin_panel/courses/create.html'
    success_url = reverse_lazy('courses:admin_course_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['major_formset'] = CourseMajorFormSet(self.request.POST)
        else:
            context['major_formset'] = CourseMajorFormSet()
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        major_formset = context['major_formset']
        
        if major_formset.is_valid():
            self.object = form.save()
            major_formset.instance = self.object
            major_formset.save()
            
            AuditLog.log(
                user=self.request.user,
                action='create',
                model_name='Course',
                object_id=self.object.id,
                object_repr=str(self.object),
                request=self.request
            )
            
            messages.success(self.request, f'تم إنشاء المقرر "{self.object.course_name}" بنجاح.')
            return redirect(self.success_url)
        
        return self.render_to_response(context)


class AdminCourseUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """تحديث مقرر"""
    model = Course
    form_class = CourseForm
    template_name = 'admin_panel/courses/update.html'
    success_url = reverse_lazy('courses:admin_course_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['major_formset'] = CourseMajorFormSet(self.request.POST, instance=self.object)
        else:
            context['major_formset'] = CourseMajorFormSet(instance=self.object)
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        major_formset = context['major_formset']
        
        if major_formset.is_valid():
            self.object = form.save()
            major_formset.save()
            
            messages.success(self.request, f'تم تحديث المقرر "{self.object.course_name}" بنجاح.')
            return redirect(self.success_url)
        
        return self.render_to_response(context)


class AdminInstructorAssignView(LoginRequiredMixin, AdminRequiredMixin, View):
    """تعيين مدرس لمقرر"""
    template_name = 'admin_panel/courses/assign_instructor.html'
    
    def get(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        instructors = User.objects.filter(role__role_name='Instructor', account_status='active')
        current_assignments = course.instructor_courses.all()
        
        return render(request, self.template_name, {
            'course': course,
            'instructors': instructors,
            'current_assignments': current_assignments
        })
    
    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        instructor_id = request.POST.get('instructor')
        is_primary = request.POST.get('is_primary') == 'on'
        
        if instructor_id:
            instructor = get_object_or_404(User, pk=instructor_id)
            
            # التحقق من عدم وجود تعيين سابق
            assignment, created = InstructorCourse.objects.get_or_create(
                instructor=instructor,
                course=course,
                defaults={'is_primary': is_primary}
            )
            
            if created:
                messages.success(request, f'تم تعيين {instructor.full_name} للمقرر {course.course_name}.')
            else:
                messages.warning(request, 'هذا المدرس معين بالفعل لهذا المقرر.')
        
        return redirect('courses:admin_instructor_assign', pk=pk)
