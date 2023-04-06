import pytz
import random
import string
from spaceone.core.service import *
from spaceone.core import config, utils
from spaceone.identity.error.error_user import *
from spaceone.identity.model import Domain, User
from spaceone.identity.manager import UserManager, DomainManager, DomainSecretManager, LocalTokenManager, EmailManager


@authentication_handler
@authorization_handler
@mutation_handler
@event_handler
class UserService(BaseService):

    def __init__(self, metadata):
        super().__init__(metadata)
        self.user_mgr: UserManager = self.locator.get_manager('UserManager')

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'domain_id'])
    def create(self, params):
        """ Create user

        Args:
            params (dict): {
                'user_id': 'str',
                'password': 'str',
                'name': 'str',
                'email': 'str',
                'user_type': 'str',
                'backend': 'str',
                'language': 'str',
                'timezone': 'str',
                'tags': 'dict',
                'domain_id': 'str'
            }

        Returns:
            user_vo (object)
        """

        params['user_type'] = params.get('user_type', 'USER')
        params['backend'] = params.get('backend', 'LOCAL')
        domain_id = params['domain_id']
        user_id = params['user_id']
        email = params.get('email')
        reset_password = params.get('reset_password', False)

        domain_mgr: DomainManager = self.locator.get_manager('DomainManager')
        domain_vo: Domain = domain_mgr.get_domain(domain_id)

        default_language = self._get_default_config(domain_vo, 'LANGUAGE')
        default_timezone = self._get_default_config(domain_vo, 'TIMEZONE')

        self._check_user_type_and_backend(params['user_type'], params['backend'], domain_vo)

        if 'language' not in params:
            params['language'] = default_language

        if 'timezone' not in params:
            params['timezone'] = default_timezone

        if 'timezone' in params:
            self._check_timezone(params['timezone'])

        if reset_password:
            params['password'] = params.get('password', self._generate_random_password())

        user_vo = self.user_mgr.create_user(params, domain_vo)
        if reset_password:
            self._check_reset_password_eligibility(params['backend'], email, user_id)

            self.user_mgr.update_user_by_vo({
                'password': self._generate_random_password(),
                'required_actions': ['UPDATE_PASSWORD']
            }, user_vo)

            token_manager: LocalTokenManager = self.locator.get_manager('LocalTokenManager')
            verify_code = token_manager.create_verify_code(domain_id, user_id)

            token = self._issue_temporary_token(user_id, domain_id)
            reset_password_link = self._get_console_sso_url(domain_id, token['access_token'], verify_code)

            email_manager: EmailManager = self.locator.get_manager('EmailManager')
            email_manager.send_reset_password_email(user_id, email, reset_password_link, params['language'])

        return user_vo

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'domain_id'])
    def update(self, params):
        """ Update user

        Args:
            params (dict): {
                'user_id': 'str',
                'password': 'str',
                'name': 'str',
                'email': 'str',
                'language': 'str',
                'timezone': 'str',
                'tags': 'dict',
                'domain_id': 'str'
            }

        Returns:
            user_vo (object)
        """

        if 'timezone' in params:
            self._check_timezone(params['timezone'])

        return self.user_mgr.update_user(params)

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'domain_id'])
    def verify_email(self, params):
        """ Verify email

        Args:
            params (dict): {
                'user_id': 'str',
                'email': 'str',
                'domain_id': 'str'
            }


        Returns:
            UserInfo
        """
        user_id = params['user_id']
        domain_id = params['domain_id']

        user_vo = self.user_mgr.get_user(user_id, domain_id)
        email = params.get('email', user_vo.email)

        token_manager: LocalTokenManager = self.locator.get_manager('LocalTokenManager')
        verify_code = token_manager.create_verify_code(domain_id, user_id)

        email_manager: EmailManager = self.locator.get_manager('EmailManager')
        email_manager.send_verification_email(user_id, email, verify_code, user_vo.language)
        params['email_verified'] = False

        return self.user_mgr.update_user(params)

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'verify_code', 'domain_id'])
    def confirm_email(self, params):
        """ Confirm email

        Args:
            params (dict): {
                'user_id': 'str',
                'verify_code': 'str',
                'domain_id': 'str'
            }


        Returns:
            None
        """

        user_id = params['user_id']
        domain_id = params['domain_id']
        verify_code = params['verify_code']

        token_manager: LocalTokenManager = self.locator.get_manager('LocalTokenManager')

        if token_manager.check_verify_code(domain_id, user_id, verify_code):
            params['email_verified'] = True
            return self.user_mgr.update_user(params)
        else:
            raise ERROR_INVALID_VERIFY_CODE(verify_code=verify_code)

    @transaction
    @check_required(['user_id', 'domain_id'])
    def reset_password(self, params):
        """ Reset password

        Args:
            params (dict): {
                'user_id': 'str',
                'domain_id': 'str'
            }

        Returns:
            None
        """

        user_vo: User = self.user_mgr.get_user(params['user_id'], params['domain_id'])
        user_id = params['user_id']
        domain_id = params['domain_id']
        backend = user_vo.backend
        email = user_vo.email
        language = user_vo.language

        self._check_reset_password_eligibility(backend, email, user_id)

        if user_vo.email_verified is False:
            raise ERROR_VERIFICATION_UNAVAILABLE(user_id=user_id)

        self.user_mgr.update_user_by_vo({'required_actions': ['UPDATE_PASSWORD']}, user_vo)
        token = self._issue_temporary_token(user_id, domain_id)

        reset_password_link = self._get_console_sso_url(domain_id, token['access_token'])

        email_manager: EmailManager = self.locator.get_manager('EmailManager')
        email_manager.send_reset_password_email(user_id, email, reset_password_link, language)

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'actions', 'domain_id'])
    def set_required_actions(self, params):
        """ Update user

        Args:
            params (dict): {
                'user_id': 'str',
                'actions': 'list',
                'domain_id': 'str'
            }

        Returns:
            user_vo (object)
        """

        new_actions = params['actions']

        user_vo: User = self.user_mgr.get_user(params['user_id'], params['domain_id'])

        if 'UPDATE_PASSWORD' in new_actions:
            if user_vo.backend == 'EXTERNAL' or user_vo.user_type == 'API_USER':
                raise ERROR_NOT_ALLOWED_ACTIONS(action='UPDATE_PASSWORD')

        required_actions = list(set(user_vo.required_actions + new_actions))

        return self.user_mgr.update_user_by_vo({'required_actions': required_actions}, user_vo)

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'domain_id'])
    def enable(self, params):
        """ Enable user

        Args:
            params (dict): {
                'user_id': 'str',
                'domain_id': 'str'
            }

        Returns:
            user_vo (object)
        """

        return self.user_mgr.enable_user(params['user_id'], params['domain_id'])

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'domain_id'])
    def disable(self, params):
        """ Disable user

        Args:
            params (dict): {
                'user_id': 'str',
                'domain_id': 'str'
            }

        Returns:
            user_vo (object)
        """

        return self.user_mgr.disable_user(params['user_id'], params['domain_id'])

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'domain_id'])
    def delete(self, params):
        """ Delete user

        Args:
            params (dict): {
                'user_id': 'str',
                'domain_id': 'str'
            }

        Returns:
            None
        """

        return self.user_mgr.delete_user(params['user_id'], params['domain_id'])

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['search', 'domain_id'])
    def find(self, params):
        """ Disable user

        Args:
            params (dict): {
                'search' (one of): {
                    'user_id': 'str',
                    'keyword': 'str'
                },
                'domain_id': 'str'
            }

        Returns:
            results(list) : 'list of {
                                'user_id': 'str',
                                'name': 'str',
                                'email': 'str',
                                'tags': 'list'
                            }'
        """

        if not any(k in params['search'] for k in ['keyword', 'user_id']):
            raise ERROR_REQUIRED_PARAMETER(key='search.keyword | search.user_id')

        domain_mgr: DomainManager = self.locator.get_manager('DomainManager')
        domain_vo: Domain = domain_mgr.get_domain(params['domain_id'])

        # Check External Authentication from Domain
        if not domain_vo.plugin_info:
            raise ERROR_NOT_ALLOWED_EXTERNAL_AUTHENTICATION()

        return self.user_mgr.find_user(params['search'], domain_vo)

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['user_id', 'domain_id'])
    def get(self, params):
        """ Get user

        Args:
            params (dict): {
                'user_id': 'str',
                'domain_id': 'str',
                'only': 'list'
            }

        Returns:
            user_vo (object)
        """

        return self.user_mgr.get_user(params['user_id'], params['domain_id'], params.get('only'))

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['domain_id'])
    @append_query_filter(['user_id', 'name', 'state', 'email', 'user_type', 'backend', 'role_id', 'domain_id'])
    @append_keyword_filter(['user_id', 'name', 'email'])
    def list(self, params):
        """ List users

        Args:
            params (dict): {
                'user_id': 'str',
                'name': 'str',
                'state': 'str',
                'email': 'str',
                'user_type': 'str',
                'backend': 'str',
                'domain_id': 'str',
                'query': 'dict (spaceone.api.core.v1.Query)'
            }

        Returns:
            results (list): 'list of user_vo'
            total_count (int)
        """

        query: dict = params.get('query', {})
        return self.user_mgr.list_users(query)

    @transaction(append_meta={'authorization.scope': 'DOMAIN'})
    @check_required(['query', 'domain_id'])
    @append_query_filter(['domain_id'])
    @append_keyword_filter(['user_id', 'name', 'email'])
    def stat(self, params):
        """
        Args:
            params (dict): {
                'domain_id': 'str',
                'query': 'dict (spaceone.api.core.v1.StatisticsQuery)'
            }

        Returns:
            values (list): 'list of statistics data'
            total_count (int)
        """

        query = params.get('query', {})
        return self.user_mgr.stat_users(query)

    def _get_domain_name(self, domain_id):
        domain_mgr: DomainManager = self.locator.get_manager('DomainManager')
        domain_vo: Domain = domain_mgr.get_domain(domain_id)
        return domain_vo.name

    def _issue_temporary_token(self, user_id, domain_id):
        # issue token
        timeout = 3600

        domain_secret_mgr: DomainSecretManager = self.locator.get_manager('DomainSecretManager')
        private_jwk = domain_secret_mgr.get_domain_private_key(domain_id=domain_id)

        local_token_manager: LocalTokenManager = self.locator.get_manager('LocalTokenManager')
        return local_token_manager.issue_temporary_token(user_id, domain_id, private_jwk=private_jwk, timeout=timeout)

    def _get_console_sso_url(self, domain_id, token, verify_code=None):
        domain_name = self._get_domain_name(domain_id)

        console_domain = config.get_global('EMAIL_CONSOLE_DOMAIN')
        console_domain = console_domain.format(domain_name=domain_name)

        if verify_code:
            return f'{console_domain}?sso_access_token={token}&verify_code={verify_code}'
        else:
            return f'{console_domain}?sso_access_token={token}'

    @staticmethod
    def _get_default_config(vo, item):
        DEFAULT = {
            'TIMEZONE': 'UTC',
            'LANGUAGE': 'en'
        }
        dict_domain = vo.to_dict()
        config = dict_domain.get('config', {})
        value = config.get(item, DEFAULT.get(item, None))
        return value

    @staticmethod
    def _check_timezone(timezone):
        if timezone not in pytz.all_timezones:
            raise ERROR_INVALID_PARAMETER(key='timezone', reason='Timezone is invalid.')

    @staticmethod
    def _check_user_type_and_backend(user_type, backend, domain_vo):
        # Check User Type and Backend
        if user_type == 'API_USER':
            if backend == 'EXTERNAL':
                raise ERROR_EXTERNAL_USER_NOT_ALLOWED_API_USER()

        # Check External Authentication from Domain
        if backend == 'EXTERNAL':
            if not domain_vo.plugin_info:
                raise ERROR_NOT_ALLOWED_EXTERNAL_AUTHENTICATION()

    @staticmethod
    def _check_reset_password_eligibility(backend, email, user_id):
        if backend == 'EXTERNAL':
            raise ERROR_UNABLE_TO_RESET_PASSWORD_IN_EXTERNAL_AUTH(user_id=user_id)
        elif email is None:
            raise ERROR_UNABLE_TO_RESET_PASSWORD_WITHOUT_EMAIL(user_id=user_id)

    @staticmethod
    def _generate_random_password():
        return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(12))
