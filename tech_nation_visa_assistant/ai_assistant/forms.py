from django import forms
from .models import AIQuery, AIFeedback

class AIQueryForm(forms.Form):
    query_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ask a question about your Tech Nation visa application...'}),
        label='',
    )

class AIFeedbackForm(forms.ModelForm):
    class Meta:
        model = AIFeedback
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional comments (optional)'}),
        }