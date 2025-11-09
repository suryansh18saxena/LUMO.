from django.urls import path
from . import views

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path('swot-analysis/', views.swot_analysis_view, name='swot_analysis'),
    path('logout/', views.logout_view, name='logout'),
    path('run-code/', views.run_code, name='run_code'), # Yeh line zaroori hai
]