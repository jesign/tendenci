from uuid import uuid4
from os.path import join
from datetime import datetime
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.core.files.storage import FileSystemStorage

#from captcha.fields import CaptchaField
from tinymce.widgets import TinyMCE

from memberships.fields import PriceInput
from models import CorporateMembershipType, CorpApp, CorpField, CorporateMembership
from corporate_memberships.utils import get_corpapp_default_fields_list, update_auth_domains
from corporate_memberships.settings import FIELD_MAX_LENGTH, UPLOAD_ROOT
from base.fields import SplitDateTimeField
from perms.utils import is_admin

fs = FileSystemStorage(location=UPLOAD_ROOT)


class CorporateMembershipTypeForm(forms.ModelForm):
    description = forms.CharField(label=_('Description'), max_length=500, required=False,
                               widget=forms.Textarea(attrs={'rows':'3'}))
    price = forms.DecimalField(decimal_places=2, widget=PriceInput(), 
                               help_text="Set 0 for free membership.")
    renewal_price = forms.DecimalField(decimal_places=2, widget=PriceInput(), required=False, 
                               help_text="Set 0 for free membership.")
    status_detail = forms.ChoiceField(
        choices=(('active','Active'),('inactive','Inactive'), ('admin hold','Admin Hold'),))
    
    class Meta:
        model = CorporateMembershipType
        fields = (
                  'name',
                  'price',
                  'renewal_price',
                  'membership_type',
                  'description',
                  'apply_threshold',
                  'individual_threshold',
                  'individual_threshold_price',
                  'admin_only',
                  'order',
                  'status',
                  'status_detail',
                  )
        
class CorpAppForm(forms.ModelForm):
    description = forms.CharField(required=False,
                             widget=TinyMCE(attrs={'style':'width:70%'}, 
                                            mce_attrs={'storme_app_label':CorpApp._meta.app_label, 
                                                       'storme_model':CorpApp._meta.module_name.lower()}),
                                                       help_text='Will show at the top of the application form.')
    confirmation_text = forms.CharField(required=False,
                             widget=TinyMCE(attrs={'style':'width:70%'}, 
                                            mce_attrs={'storme_app_label':"confirmation_text", 
                                                       'storme_model':"confirmation_text"}),
                                                       help_text='Will show on the confirmation page.')
    notes = forms.CharField(label=_('Notes'), required=False,
                               widget=forms.Textarea(attrs={'rows':'3'}),
                               help_text='Notes for editor. Will not display on the application form.')
    status_detail = forms.ChoiceField(
        choices=(('active','Active'),('inactive','Inactive'), ('admin hold','Admin Hold'),))
    
    class Meta:
        model = CorpApp
        fields = (
                  'name',
                  'slug',
                  'corp_memb_type',
                  'authentication_method',
                  'description',
                  'confirmation_text',
                  'notes',
                  #'use_captcha',
                  #'require_login',
                  'status',
                  'status_detail',
                  )
        

default_corpapp_inline_fields_list = get_corpapp_default_fields_list()
if default_corpapp_inline_fields_list:
    required_corpapp_inline_fields_list = [str(field_d['field_name']) for field_d in default_corpapp_inline_fields_list if field_d['required']]
else:
    required_corpapp_inline_fields_list = []
    
class CorpFieldForm(forms.ModelForm):
    instruction = forms.CharField(label=_('Instruction for User'), max_length=500, required=False,
                               widget=forms.Textarea(attrs={'rows':'3'}))
    field_name = forms.CharField(label=_(''), max_length=30, required=False,
                               widget=forms.HiddenInput())
    
    class Meta:
        model = CorpField
        fields = (
                  'label',
                  'field_name',
                  #'object_type',
                  'field_type',
                  'size',
                  'choices',
                  'field_layout',
                  'required',
                  'visible',
                  'no_duplicates',
                  'instruction',
                  'default_value',
                  'admin_only',
                  'css_class',
                  'order'
                  )
        
    def __init__(self, *args, **kwargs): 
        super(CorpFieldForm, self).__init__(*args, **kwargs)
        
        instance = getattr(self, 'instance', None)
        if instance and instance.id:
            if instance.field_name in required_corpapp_inline_fields_list and instance.required:
                self.fields['required'].widget.attrs['disabled'] = "disabled"
                self.fields['visible'].widget.attrs['disabled'] = "disabled"
            if instance.field_name == 'name':
                self.fields['no_duplicates'].widget.attrs['disabled'] = "disabled"
                
    def clean_required(self):
        if self.instance.field_name in required_corpapp_inline_fields_list and self.instance.required:
            return self.instance.required
        return self.cleaned_data['required']
        
    def clean_visible(self):
        if self.instance.field_name in required_corpapp_inline_fields_list and self.instance.visible:
            return self.instance.visible
        return self.cleaned_data['visible']
    
    def clean_no_duplicates(self):
        if self.instance.field_name == 'name' and self.instance.no_duplicates:
            return self.instance.no_duplicates
        return self.cleaned_data['no_duplicates']
    
    
class CorpMembForm(forms.ModelForm):
    status_detail = forms.ChoiceField(
        choices=(('active','Active'),
                 ('pending','Pending'),
                 ('paid - pending approval','Paid - Pending Approval'),
                 ('admin hold','Admin Hold'),
                 ('inactive','Inactive'), 
                 ('expired','Expired'),
                 ('archive','Archive'),))
    join_dt = SplitDateTimeField(label=_('Join Date/Time'),
        initial=datetime.now())
    expiration_dt = SplitDateTimeField(label=_('Expiration Date/Time'))
    
    class Meta:
        model = CorporateMembership
        exclude = ('corp_app', 'guid', 'renewal', 'invoice', 'renew_dt', 
                   'approved', 'approved_denied_dt',
                   'approved_denied_user',
                   'creator_username', 'owner', 'owner_username')
        
    def __init__(self, corp_app, field_objs, *args, **kwargs):
        """
            Dynamically build the form fields.
        """
        self.corp_app = corp_app
        self.field_objs = field_objs
        super(CorpMembForm, self).__init__(*args, **kwargs)

        for field in field_objs:
            if field.field_type not in ['section_break', 'page_break']:
                if field.field_name:
                    field_key = field.field_name
                else:
                    field_key = "field_%s" % field.id
                
                self.fields[field_key] = field.get_field_class()
                if not field.field_name and self.instance:
                    self.fields[field_key].initial = field.get_value(self.instance)
            
        #self.fields['captcha'] = CaptchaField(label=_('Type the code below'))
        
    def clean_corporate_membership_type(self):
        if self.cleaned_data['corporate_membership_type']:
            return CorporateMembershipType.objects.get(pk=int(self.cleaned_data['corporate_membership_type']))
        return self.cleaned_data['corporate_membership_type']
        
    def save(self, user,  **kwargs):
        """
            Create a CorporateMembership instance and related CorpFieldEntry instances for each 
            form field.
        """
        corporate_membership = super(CorpMembForm, self).save(commit=False)
        corporate_membership.corp_app = self.corp_app
        
        corporate_membership.owner = user
        corporate_membership.owner_username = user.username
        
        if not self.instance.pk:
            mode = 'add'
        else:
            mode = 'edit'
            
        if mode == 'add':
            corporate_membership.creator = user
            corporate_membership.creator_username = user.username
            
            if not is_admin(user):
                corporate_membership.status = 1
                corporate_membership.status_detail = 'pending'
                corporate_membership.join_dt = datetime.now()
            
            # calculate the expiration dt
        
        corporate_membership.save()

        for field_obj in self.field_objs:
            if (not field_obj.field_name) and field_obj.field_type not in ['section_break', 'page_break']:
                field_key = "field_%s" % field_obj.id
                value = self.cleaned_data[field_key]
                if value and self.fields[field_key].widget.needs_multipart_form:
                    value = fs.save(join("forms", str(uuid4()), value.name), value)
                # if the value is a list convert is to a comma delimited string
                if isinstance(value,list):
                    value = ','.join(value)
                if not value: value=''
                
                if hasattr(field_obj, 'entry'):
                    field_obj.entry.value = value
                    field_obj.entry.save()
                else:
                    corporate_membership.fields.create(field_id=field_obj.id, value=value)
                    
        # update authorized domain if needed
        if self.corp_app.authentication_method == 'email':
            update_auth_domains(corporate_membership, corporate_membership.authorized_domains)
        
        return corporate_membership
        
        
            
        