from django import forms
from .models import Document, DocumentComment

class DocumentForm(forms.ModelForm):
    """General document form"""
    class Meta:
        model = Document
        fields = ['title', 'related_criteria', 'status', 'file']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

class PersonalStatementForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'content', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': 'Enter title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'rows': 15,
                'placeholder': 'Write your personal statement here...'
            }),
            'status': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
            })
        }

class CVForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'content', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': 'Enter CV title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'rows': 15,
                'placeholder': 'Write your CV content here...'
            }),
            'status': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
            })
        }

class DocumentCommentForm(forms.ModelForm):
    """Form for document comments"""
    class Meta:
        model = DocumentComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }