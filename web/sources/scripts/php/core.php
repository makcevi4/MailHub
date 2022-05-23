<?php
$configs = parse_ini_file((substr($_SERVER['DOCUMENT_ROOT'], -1) !== '/' ? $_SERVER['DOCUMENT_ROOT'].'/sources/data/configs.ini' : $_SERVER['DOCUMENT_ROOT'].'sources/data/configs.php'), true);

class Database {
    public function __construct($configs){
        $this->configs = $configs;
        $this->database = $this->connect();
    }

    public function connect(){
        $database = new mysqli(
            $this->configs['database']['host'],
            $this->configs['database']['username'],
            $this->configs['database']['password'],
            $this->configs['database']['name'],
            $this->configs['database']['port']
        );

        if ($database->connect_errno){
            echo "Connection failed to MySQL: ".$database->connect_error;
            return null;
        }
        else{
            return $database;
        }
    }

    public function getDataByValue($table, $value, $data, $_data=NULL, $_value=NULL){
        if (is_null($_value) && is_null($_data)){
            if (is_int($data)){
                $query = "SELECT * FROM `{$table}` WHERE `{$value}` = {$data}";
            }
            else {
                $query = "SELECT * FROM `{$table}` WHERE `{$value}` = '{$data}'";
            }
        }
        else {
            if (is_int($data)){
                if (is_int($_data)){
                    $query = "SELECT * FROM `{$table}` WHERE `{$value}` = {$data} OR `{$_value}` = {$_data}";
                }
                else {
                    $query = "SELECT * FROM `{$table}` WHERE `{$value}` = {$data} OR `{$_value}` = '{$_data}'";
                }
            }
            else {
                if (is_int($_data)) {
                    $query = "SELECT * FROM `{$table}` WHERE `{$value}` = '{$data}' OR `{$_value}` = {$_data}";
                }
                else {
                    $query = "SELECT * FROM `{$table}` WHERE `{$value}` = '{$data}' OR `{$_value}` = '{$_data}'";
                }
            }
        }

        return mysqli_fetch_assoc(mysqli_query($this->database, $query));
    }

}

class Handler {
    public function __construct($database, $formatter){
        $this->database = $database;
        $this->formatter = $formatter;
    }

    public function checkUserAgent($userdata){
        $output = array('status' => false, 'description' => null);
        $userAgent = $this->formatter->getUserAgent();
        $existAgentData = $this->database->getDataByValue('users', 'agent', $userAgent);

        echo '<br>'.$userAgent.'<br>';
        if (isset($existAgentData)){
            echo ' - exist agent - ';
            if ($userdata['id'] == $existAgentData['id']){
                // проверка на демо
                echo 'проверка демо';
            }
            else {
                // другой пользователь
                $output['description'] = 'incorrect-id';
                echo 'другой пользователь';
            }

        }
        else {
            echo ' - didn\'t exist agent - ';

            if (empty($userdata['agent'])) {
                echo 'Демо';
            }
            else {
                if ($userdata['agent'] == $userAgent){
                    // проверка демо
                    echo 'проверка демо';
                }
                else {
                    $output['description'] = 'incorrect-agent';
                    echo 'другой агент';
                }
            }


        }

        echo '<br><br><br>EX: ';
        print_r($existAgentData);
        echo '<br>';

        echo 'UA: ';
        print_r($userdata);
        echo '<br>';


        return $output;
    }

    public function sendPost($link, $data){
        $ch = curl_init();

        curl_setopt($ch,CURLOPT_URL, $link);
        curl_setopt($ch,CURLOPT_POST, true);
        curl_setopt($ch,CURLOPT_POSTFIELDS, $data);

        curl_setopt($ch,CURLOPT_RETURNTRANSFER, true);

        curl_exec($ch);
    }
}

class Formatter {
    public function getUserAgent(){
        $result = NULL;
        $value = 'AppleWebKit/';

        foreach (explode(' ', $_SERVER['HTTP_USER_AGENT']) as $data){
            if (is_int(strpos($data, $value))){
                $result =  str_replace($value, '', $data);
            }

        }

        return $result;
    }

}

$database = new Database($configs);
$formatter = new Formatter();
$handler = new Handler($database, $formatter);
?>
