from django.db import models


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=150)
    publisher = models.CharField(max_length=150, blank=True)
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.title