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
        $handler->checkUserAgent($userdata);
        ?>
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
    <form id="demo">
        <input required type="number" name='id' placeholder="Введи свой ID" minlength="10" maxlength="11">
        <button type="button" id="get-access">Получить</button>
    </form>

<?php endif; ?>


</body>
</html>
