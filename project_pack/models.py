from django.db import models
from django.utils import timezone


# Create your models here.
class Project(models.Model):
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.name} | {self.code}'


current_project = Project.objects.get(code='sporty_credit')


class ProjectQuerySet(models.QuerySet):
    def select_project(self):
        return self.filter(project=current_project)


class ProjectManager(models.Manager):
    def get_queryset(self):
        return ProjectQuerySet(self.model, using=self._db).select_project()

    def create(self, *args, **kwargs):
        # Ensure the condition is applied on create
        kwargs['project'] = current_project
        return super().create(*args, **kwargs)

    def update_or_create(self, *args, **kwargs):
        # Ensure the condition is applied on update or create
        defaults = kwargs.get('defaults', {})
        defaults['project'] = current_project
        kwargs['defaults'] = defaults
        return super().update_or_create(*args, **kwargs)

    def save_instance(self, instance, *args, **kwargs):
        # Ensure the condition is applied on save
        instance.project = current_project
        instance.save(*args, **kwargs)


