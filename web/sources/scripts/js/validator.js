$(function(){
    let linkData = window.location.href.split('/');
    let page = linkData.slice(-1)[0];

    FormValidator(page);
});

function FormValidator(page){
    switch (page){
        case 'demo':
            var input = null;
            var button = null;

            $('#' + page).find ('input, button').each(function() {
                if (this.type === 'button'){
                    button = $('#' + this.id);
                }
                else {
                    input = $('input[name=' + this.name + ']');
                }
            });

            input.keyup(function() {
                let field = input.val();
                input.css({'box-shadow': 'none'});

                if (field.length > 9 && field.length < 12) {
                    if (input.attr('class') === 'error'){
                        input.removeClass('error');
                    }
                    input.addClass('success');
                }
                else {
                    if (input.attr('class') === 'success'){
                        input.removeClass('success');
                    }
                    input.addClass('error');
                }
            });

            button.bind('click', function(){
                let field = input.val();

                if (field.length > 9 && field.length < 12){
                    window.location.href = window.location.href + '?id=' + input.val()
                }
                else {
                    input.css({'outline': 'none', 'box-shadow': '0px 0px 10px 1px #FF0000'});
                }
            });
            break;

        case '':
            console.log('empty');
    }
}