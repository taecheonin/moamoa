/**
 * TCI MoaMoa 메인 JavaScript 파일
 * 
 * 랜딩 페이지의 인터랙티브 기능을 구현합니다.
 * 
 * @package TCI_MoaMoa
 * @since 1.0.0
 */

(function($) {
    'use strict';

    // 전역 변수
    var tciMoamoaApp = {
        // 모바일 메뉴 상태
        tciMobileMenuOpen: false,
        
        // 채팅 메시지 배열
        tciChatMessages: [
            { id: 1, sender: 'bot', text: '안녕! 오늘 학용품 산 거 있어?' }
        ],
        
        // 타이핑 상태
        tciIsTyping: false
    };

    /**
     * 문서 준비 완료 시 초기화
     */
    $(document).ready(function() {
        tciMoamoaApp.tciInitMobileMenu();
        tciMoamoaApp.tciInitChatDemo();
        tciMoamoaApp.tciInitPolicyModal();
        tciMoamoaApp.tciInitSmoothScroll();
        
        // Lucide 아이콘 초기화 (로드 후)
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    });

    /**
     * 모바일 메뉴 초기화
     */
    tciMoamoaApp.tciInitMobileMenu = function() {
        var $tciToggleBtn = $('#tci-mobile-menu-toggle');
        var $tciMobileMenu = $('#tci-mobile-menu');
        var $tciMenuLinks = $('.tci-mobile-menu-link');

        // 토글 버튼 클릭 이벤트
        $tciToggleBtn.on('click', function() {
            tciMoamoaApp.tciMobileMenuOpen = !tciMoamoaApp.tciMobileMenuOpen;
            
            if (tciMoamoaApp.tciMobileMenuOpen) {
                $tciMobileMenu.removeClass('hidden');
                $tciToggleBtn.html('<i data-lucide="x" class="w-6 h-6"></i>');
            } else {
                $tciMobileMenu.addClass('hidden');
                $tciToggleBtn.html('<i data-lucide="menu" class="w-6 h-6"></i>');
            }
            
            // Lucide 아이콘 재생성
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        });

        // 메뉴 링크 클릭 시 메뉴 닫기
        $tciMenuLinks.on('click', function() {
            $tciMobileMenu.addClass('hidden');
            $tciToggleBtn.html('<i data-lucide="menu" class="w-6 h-6"></i>');
            tciMoamoaApp.tciMobileMenuOpen = false;
            
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        });

        // 드롭다운 메뉴 외부 클릭 시 닫기
        $(document).on('click', function(e) {
            if (!$(e.target).closest('#tci-features-dropdown').length) {
                // 드롭다운 외부 클릭 시 처리 (필요시)
            }
        });
    };

    /**
     * 채팅 데모 초기화
     */
    tciMoamoaApp.tciInitChatDemo = function() {
        var $tciChatMessages = $('#tci-chat-messages');
        var $tciQuickInput = $('#tci-quick-input');
        var $tciChatSend = $('#tci-chat-send');

        // 채팅 메시지 렌더링 함수
        function tciRenderMessages() {
            var tciHtml = '';
            
            tciMoamoaApp.tciChatMessages.forEach(function(tciMsg) {
                if (tciMsg.sender === 'user') {
                    tciHtml += '<div class="flex justify-end">';
                    tciHtml += '<div class="max-w-[80%] p-3 rounded-2xl text-sm bg-blue-500 text-white rounded-tr-none">';
                    tciHtml += tciMsg.text;
                    tciHtml += '</div></div>';
                } else {
                    tciHtml += '<div class="flex justify-start">';
                    tciHtml += '<div class="w-8 h-8 bg-yellow-400 rounded-full flex items-center justify-center mr-2 text-white font-bold text-xs flex-shrink-0">M</div>';
                    tciHtml += '<div class="max-w-[80%] p-3 rounded-2xl text-sm bg-gray-100 text-gray-800 rounded-tl-none">';
                    tciHtml += tciMsg.text;
                    tciHtml += '</div></div>';
                }
            });
            
            if (tciMoamoaApp.tciIsTyping) {
                tciHtml += '<div class="flex justify-start">';
                tciHtml += '<div class="w-8 h-8 bg-yellow-400 rounded-full flex items-center justify-center mr-2 text-white font-bold text-xs">M</div>';
                tciHtml += '<div class="bg-gray-100 p-3 rounded-2xl rounded-tl-none text-xs text-gray-500">';
                tciHtml += '입력 중...';
                tciHtml += '</div></div>';
            }
            
            $tciChatMessages.html(tciHtml);
            
            // 스크롤을 맨 아래로
            $tciChatMessages.scrollTop($tciChatMessages[0].scrollHeight);
        }

        // 초기 메시지 렌더링
        tciRenderMessages();

        // 빠른 입력 버튼 클릭
        $tciQuickInput.on('click', function() {
            var tciInputText = $(this).text().replace(/"/g, '');
            tciMoamoaApp.tciHandleChatSend(tciInputText);
        });

        // 전송 버튼 클릭 (현재는 빠른 입력만 지원)
        $tciChatSend.on('click', function() {
            var tciInputText = $tciQuickInput.text().replace(/"/g, '');
            if (tciInputText.trim()) {
                tciMoamoaApp.tciHandleChatSend(tciInputText);
            }
        });
    };

    /**
     * 채팅 메시지 전송 처리
     */
    tciMoamoaApp.tciHandleChatSend = function(tciInputText) {
        if (!tciInputText.trim() || tciMoamoaApp.tciIsTyping) {
            return;
        }

        // 사용자 메시지 추가
        var tciUserMsg = {
            id: Date.now(),
            sender: 'user',
            text: tciInputText
        };
        
        tciMoamoaApp.tciChatMessages.push(tciUserMsg);
        tciMoamoaApp.tciIsTyping = true;
        tciMoamoaApp.tciRenderMessages();

        // 봇 응답 시뮬레이션
        setTimeout(function() {
            var tciBotResponse = '알겠어! 기록해둘게.';
            
            if (tciInputText.includes('공책') || tciInputText.includes('연필') || tciInputText.includes('문구점')) {
                tciBotResponse = '오, 공부 열심히 하려나보다! 📚 [학용품]으로 3,000원 기록 완료! 참 잘했어!';
            } else if (tciInputText.includes('과자') || tciInputText.includes('떡볶이')) {
                tciBotResponse = '맛있게 먹었니? 😋 [간식]으로 분류했어. 이번 달 간식비가 조금 많아지는데 주의해볼까?';
            }
            
            tciMoamoaApp.tciChatMessages.push({
                id: Date.now() + 1,
                sender: 'bot',
                text: tciBotResponse
            });
            
            tciMoamoaApp.tciIsTyping = false;
            tciMoamoaApp.tciRenderMessages();
        }, 1500);
    };

    /**
     * 채팅 메시지 렌더링 (전역 함수)
     */
    tciMoamoaApp.tciRenderMessages = function() {
        var $tciChatMessages = $('#tci-chat-messages');
        var tciHtml = '';
        
        tciMoamoaApp.tciChatMessages.forEach(function(tciMsg) {
            if (tciMsg.sender === 'user') {
                tciHtml += '<div class="flex justify-end">';
                tciHtml += '<div class="max-w-[80%] p-3 rounded-2xl text-sm bg-blue-500 text-white rounded-tr-none">';
                tciHtml += tciMsg.text;
                tciHtml += '</div></div>';
            } else {
                tciHtml += '<div class="flex justify-start">';
                tciHtml += '<div class="w-8 h-8 bg-yellow-400 rounded-full flex items-center justify-center mr-2 text-white font-bold text-xs flex-shrink-0">M</div>';
                tciHtml += '<div class="max-w-[80%] p-3 rounded-2xl text-sm bg-gray-100 text-gray-800 rounded-tl-none">';
                tciHtml += tciMsg.text;
                tciHtml += '</div></div>';
            }
        });
        
        if (tciMoamoaApp.tciIsTyping) {
            tciHtml += '<div class="flex justify-start">';
            tciHtml += '<div class="w-8 h-8 bg-yellow-400 rounded-full flex items-center justify-center mr-2 text-white font-bold text-xs">M</div>';
            tciHtml += '<div class="bg-gray-100 p-3 rounded-2xl rounded-tl-none text-xs text-gray-500">';
            tciHtml += '입력 중...';
            tciHtml += '</div></div>';
        }
        
        $tciChatMessages.html(tciHtml);
        
        // 스크롤을 맨 아래로
        $tciChatMessages.scrollTop($tciChatMessages[0].scrollHeight);
    };

    /**
     * 정책 모달 초기화
     */
    tciMoamoaApp.tciInitPolicyModal = function() {
        var $tciModal = $('#tci-policy-modal');
        var $tciModalTitle = $('#tci-modal-title');
        var $tciModalContent = $('#tci-modal-content');
        var $tciModalBackdrop = $('#tci-modal-backdrop');
        var $tciModalClose = $('#tci-modal-close');
        var $tciModalConfirm = $('#tci-modal-confirm');
        var $tciOpenTerms = $('#tci-open-terms');
        var $tciOpenPrivacy = $('#tci-open-privacy');

        // 모달 열기 함수
        function tciOpenModal(tciType) {
            var tciTitle = tciType === 'terms' ? '이용약관' : '개인정보처리방침';
            var tciContent = '';
            
            if (typeof window.tciMoamoaPolicyData !== 'undefined') {
                tciContent = tciType === 'terms' 
                    ? window.tciMoamoaPolicyData.terms 
                    : window.tciMoamoaPolicyData.privacy;
            }
            
            $tciModalTitle.text(tciTitle);
            $tciModalContent.text(tciContent);
            $tciModal.removeClass('hidden');
            document.body.style.overflow = 'hidden';
            
            // Lucide 아이콘 재생성
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        }

        // 모달 닫기 함수
        function tciCloseModal() {
            $tciModal.addClass('hidden');
            document.body.style.overflow = 'unset';
        }

        // 이용약관 열기
        $tciOpenTerms.on('click', function(e) {
            e.preventDefault();
            tciOpenModal('terms');
        });

        // 개인정보처리방침 열기
        $tciOpenPrivacy.on('click', function(e) {
            e.preventDefault();
            tciOpenModal('privacy');
        });

        // 모달 닫기 이벤트
        $tciModalBackdrop.on('click', tciCloseModal);
        $tciModalClose.on('click', tciCloseModal);
        $tciModalConfirm.on('click', tciCloseModal);
    };

    /**
     * 부드러운 스크롤 초기화
     */
    tciMoamoaApp.tciInitSmoothScroll = function() {
        $('a[href^="#"]').on('click', function(e) {
            var tciTarget = $(this.getAttribute('href'));
            
            if (tciTarget.length) {
                e.preventDefault();
                $('html, body').stop().animate({
                    scrollTop: tciTarget.offset().top - 80
                }, 800);
            }
        });
    };

    // 전역 객체로 노출
    window.tciMoamoaApp = tciMoamoaApp;

})(jQuery);

