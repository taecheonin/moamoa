var kakaoLoginButton = document.querySelector('.kakao-login');
if (kakaoLoginButton) {
    kakaoLoginButton.addEventListener('click', function () {
        location.href = 'https://kauth.kakao.com/oauth/authorize?response_type=code&client_id=d0676b6a43eee5060c15c2f4f33cd546&redirect_uri=http://localhost:8000/api/v1/accounts/auth/kakao/callback/';
    });
}

var kidsLoginButton = document.querySelector('.kids-login');
if (kidsLoginButton) {
    kidsLoginButton.addEventListener('click', function () {
        location.href = '/login/';
    });
}

var addAccountButton = document.querySelector('.add-account');
if (addAccountButton) {
    addAccountButton.addEventListener('click', function () {
        location.href = '/signup/';
    });
}