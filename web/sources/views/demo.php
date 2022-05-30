<?php
$core = include_once (substr($_SERVER['DOCUMENT_ROOT'], -1) !== '/' ? $_SERVER['DOCUMENT_ROOT'].'/sources/scripts/php/core.php' : $_SERVER['DOCUMENT_ROOT'].'sources/scripts/php/core.php');
$user = isset($_GET['id']) ? $_GET['id'] : NULL;
$userdata = $database->getDataByValue('users', 'id', $user);

//$result = $handler->checkUserAgent($user);
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>Получение пробной подписки</title>
    <link rel="stylesheet" href="/sources/styles/demo.css">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.5.0/font/bootstrap-icons.css" rel="stylesheet" type="text/css" />
    <link href="https://fonts.googleapis.com/css?family=Lato:300,400,700,300italic,400italic,700italic" rel="stylesheet" type="text/css" />
    <link href="/sources/styles/styles.css" rel="stylesheet" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
    <script src="/sources/scripts/js/validator.js"></script>
</head>
<body>
<!-- got ID -->
<?php if(!is_null($user)):?>
    <?php if (is_null($userdata)): ?>
        <?php
        setcookie('error', 'empty-userdata', time() + 60, '/demo');
        setcookie('id', $user, time() + 60, '/demo');
        header('Location: /demo');
        ?>
    <?php else: ?>
        <?php
        $result = $handler->checkBan();
        $handler->setIP($userdata);

        if ($result['status']){
            $result = $handler->checkUserDemoSubscription($userdata);
        }
        ?>

        <?php if($result['status'] && $result['description'] == 'success'): ?>
            <!-- Submit success message-->
            <div class="block-success d-none" id="submitSuccessMessage">
                <div class="text-center mb-3">
                    <div class="fw-bolder">Подписка успешно выдана</div>
                    <p>Для дальнейших деталей перейдите в Telegram</p>
                </div>
            </div>
        <?php else: ?>
            <div class="block-error">
                <?php switch ($result['description']):
                    case 'already-used': ?>
                        <!-- Submit error message-->
                        <div class="error-used d-none" id="submitErrorMessage">
                            <div class="text-center text-danger mb-3">
                                Подписка ранее была оформлена.
                                Получить подписку можно всего лишь один раз
                            </div>
                        </div>
                    <?php break;
                        case 'another-user': ?>
                        <div class="error-blocked d-none" id="submitErrorMessage">
                            <div class="text-center text-danger mb-3">
                                Ты попытался оформить пробную подписку не на себя, поэтому твой профиль был заблокирован.
                                Если считаешь это ошибкой - обратись в поддержку.
                            </div>
                        </div>
                    <?php break;
                        case 'another-agent': ?>
                        <div class="error-agent d-none" id="submitErrorMessage">
                            <div class="text-center text-danger mb-3">
                                Ошибка устройства. Ранее за твоим аккаунтом было привязано другое устройство.
                            </div>
                        </div>

                        <?php break; ?>
                    <?php endswitch; ?>
            </div>
        <?php endif; ?>
    <?php endif; ?>

<!-- didn't got ID -->
<?php else: ?>
    <?php
    if(isset($_COOKIE['error']) && $_COOKIE['error'] == 'empty-userdata'){
        echo "<div class='notification-error'>Пользователя с ID {$_COOKIE['id']} нет в базе</div>";

        unset($_COOKIE['error']);
        unset($_COOKIE['id']);

        setcookie('error', null, -1, '/demo');
        setcookie('id', null, -1, '/demo');
    };
    ?>
    <header class="masthead">
        <div class="container position-relative">
            <div class="row justify-content-center">
                <div class="col-xl-6">
                    <div class="text-center text-white">
                        <h1 class="mb-5">Чтобы получить пробную подписку и протестировать Наш сервис введите свой Telegram ID</h1>
                        <form class="form-subscribe" id="demo" data-sb-form-api-token="API_TOKEN">
                            <!-- Email address input-->
                            <div class="row">
                                <div class="col">
                                    <input class="form-control form-control-lg" required type="number" name='id' placeholder="Введи свой ID" minlength="10" maxlength="11">
                                    <div class="col-auto">
                                        <button class="btn btn-primary btn-lg disabled" type="button" id="get-access">Получить</button>
                                    </div>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </header>
<?php endif; ?>
<!-- Image Showcases-->
    <section class="showcase">
        <div class="container-fluid p-0">
            <div class="row g-0">
                <div class="col-lg-6 order-lg-2 text-white showcase-img" style="background-image: url('/sources/views/assets/img/bg-showcase-1.jpg')"></div>
                <div class="col-lg-6 order-lg-1 my-auto showcase-text">
                    <h2>Почему нужно выбирать нас!</h2>
                    <p class="lead mb-0">Мы достаточно долго работаем в данной сфере и знаем, что нужно нашим
                        клиентам, а наши цены, по сравнению цена-качество, ниже рыночных! </p>
                </div>
            </div>
            <div class="row g-0">
                <div class="col-lg-6 text-white showcase-img" style="background-image: url('/sources/views/assets/img/bg-showcase-2.jpg')"></div>
                <div class="col-lg-6 my-auto showcase-text">
                    <h2>В чем наше преимущество?</h2>
                    <p class="lead mb-0">Наш код написан профессионалами, что дает один весомый плюс! Какой спросите Вы? Это практически безотказная работа сервиса!</p>
                </div>
            </div>
            <div class="row g-0">
                <div class="col-lg-6 order-lg-2 text-white showcase-img" style="background-image: url('/sources/views/assets/img/bg-showcase-3.jpg')"></div>
                <div class="col-lg-6 order-lg-1 my-auto showcase-text">
                    <h2>Мы лояльны к нашим клиентам!</h2>
                    <p class="lead mb-0">У нас отзывчивая служба поддержки, мы готовы к любым предложениям по улучшению качества работы. Также, при желании,
                        Вы можете стать участником реферальной программы, которая даст Вам приятный бонусы! На все подробности Вам ответит служба поддержки.</p>
                </div>
            </div>
        </div>
    </section>
    <!-- Call to Action-->
    <section class="call-to-action text-white text-center" id="signup">
        <div class="container position-relative">
            <div class="row justify-content-center">
                <div class="col-xl-6">
                    <h2 class="mb-4">Готовы к нам присоединиться? Вводи Telegram ID и погнали!</h2>
                </div>
            </div>
        </div>
    </section>
</body>
</html>
