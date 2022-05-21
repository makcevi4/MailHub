<?php
switch($_GET['query']){
    case '':
        require 'sources/templates/header.php';
        require 'sources/views/main.php';
        require 'sources/templates/footer.php';
        break;

    case 'demo':
        require 'sources/views/demo.php';
        break;

}

?>