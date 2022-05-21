<?php
$core = include_once (substr($_SERVER['DOCUMENT_ROOT'], -1) !== '/' ? $_SERVER['DOCUMENT_ROOT'].'/sources/scripts/php/core.php' : $_SERVER['DOCUMENT_ROOT'].'sources/scripts/php/core.php');
$user = isset($_GET['id']) ? $_GET['id'] : NULL;
$result = $handler->checkUserAgent($user);
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>Получение пробной подписки</title>
    <link rel="stylesheet" href="sources/styles/demo.css">
</head>
<body>

<!-- Если есть GET-запрос с ID пользователя-->
<?php if(!is_null($user)):

?>
    <?php if($result): ?>
        <!-- Здесь должна  подключаться страница об успешном подключении демо -->


<!-- Если нет GET-запроса с ID пользователя -->
<?php else: ?>
    <!--
    Тут должна быть форма с POST-запросом, которая через AJAX будет отправлять ID на
    -->
<?php endif; ?>


</body>
</html>
