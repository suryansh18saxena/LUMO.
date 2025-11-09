from django.db import models
from django.conf import settings

class chats(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    user_input = models.TextField()
    bot_reply = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True) # New field

    def __str__(self):
        return f"Chat by {self.user.username} at {self.timestamp}"