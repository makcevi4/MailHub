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

    public function getData(){

    }

    public function getDataByValue($table, $value, $data, $_data=NULL, $_value=NULL, $mode='item'){
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

        $result = mysqli_query($this->database, $query);

        if ($mode == 'array'){
            $result = mysqli_fetch_all($result);
        }
        else {
            $result = mysqli_fetch_assoc($result);
        }

        return $result;
    }

    public function addData($table, $data){
        $query = null;

        switch ($table){
            case 'logs':
                $query = "INSERT INTO `{$table}` (`user`, `username`, `usertype`, `date`, `action`) VALUES ({$data['user']}, '{$data['username']}', '{$data['usertype']}', NOW(), '{$data['action']}')";
                break;
            case 'users':
                $query = "2";
                break;
            case 'subscriptions':
                $query = "INSERT INTO `{$table}` (`type`, `user`, `status`, `purchased`, `expiration`) VALUES ('{$data['type']}', {$data['user']}, 'processed', '{$data['dates']['now']}', '{$data['dates']['expiration']}')";
                break;
            case 'payments':
                $query = "4";
                break;
            case 'domains':
                $query = "5";
                break;
            case 'mailings':
                $query = "6";
                break;
        }

//        if (!$this->database->query($query)) {
//            printf("Error message: %s\n", $this->database->error);
//        }
        return mysqli_query($this->database, $query);

//
//                    case 'users':
//                        query = f"""
//                        INSERT INTO `{table}` (
//                        `id`, `name`, `registration`, `balance`, `inviter`, `percentage`, `ban`, `cause`)
//                        VALUES (
//                        {items['id']}, '{items['name']}', {int(time.time())}, 0,
//                        {items['inviter']}, {items['percentage']}, 0, 'None')
//                        """
//
//                    case 'subscriptions':
//                        status = list(self.configs['subscriptions']['statuses'].keys())[0]
//
//                        query = f"""
//                        INSERT INTO `{table}` (`type`, `user`, `status`, `purchased`, `expiration`)
//                        VALUES (
//                        '{items['type']}', {items['user']}, '{status}',
//                        {items['dates']['now']}, {items['dates']['expiration']})
//                        """
//
//                    case 'payments':
//                        status = list(self.configs['payments']['statuses'].keys())[1]
//                        query = f"""
//                        INSERT INTO `{table}` (`id`, `date`, `status`, `type`, `user`, `summary`, `expiration`)
//                        VALUES (
//                        {items['id']}, {int(time.time())}, '{status}', '{items['type']}',
//                        {items['user']}, {items['summary']}, {items['expiration']})
//                        """
//
//                    case 'domains':
//                        query = f"""
//                        INSERT INTO `{table}` (`domain`, `status`, `registration`)
//                        VALUES ('{items['domain']}', '{items['status']}', {int(time.time())})
//                        """
//
//                    case 'mailings':
//                        status = list(self.configs['statuses'].keys())[1]
//                        query = f"""
//                        INSERT INTO `{table}` (`id`, `date`, `status`, `domain`, `user`, `mail `)
//                        VALUES ({items['id']}, {int(time.time())}, '{status}',
//                        '{items['domain']}', {items['user']}, '{items['mail']}')
//                        """
    }

    public function changeData($table, $setter, $data, $value, $column='id'){
        if(is_int($data) || is_float($data)){
            if(is_int($value)){
                $query = "UPDATE `{$table}` SET `{$setter}` = {$data} WHERE `{$table}`.`{$column}` = {$value}";
            }
            else {
                $query = "UPDATE `{$table}` SET `{$setter}` = {$data} WHERE `{$table}`.`{$column}` = '{$value}'";
            }
        }
        elseif (is_string($data)){
            if (is_string($value) || is_float($value)){
                $query = "UPDATE `{$table}` SET `{$setter}` = '{$data}' WHERE `{$table}`.`{$column}` = {$value}";
            }
            else {
                $query = "UPDATE `{$table}` SET `{$setter}` = '{$data}' WHERE `{$table}`.`{$column}` = '{$value}'";
            }
        }
        else {
            $query = "UPDATE `{$table}` SET `{$setter}` = '{$data}' WHERE `{$table}`.`{$column}` = {$value}"; // array
        }

        return mysqli_query($this->database, $query);

    }



}

class Handler {
    public function __construct($configs, $database, $formatter){
        $this->configs = $configs;
        $this->database = $database;
        $this->formatter = $formatter;
    }

    public function checkBan(){
        $output = ['status' => true, 'description' => 'not-banned'];
        $userAgent = $this->formatter->getUserAgent();
        $userdata = $this->database->getDataByValue('users', 'agent', $userAgent);

        if (!is_null($userdata) && intval($userdata['ban'])){
            $output['status'] = false;
            $output['description'] = 'banned';
        }

        return $output;
    }

    public function setIP($userdata){
        $ip = $_SERVER['REMOTE_ADDR'];

        if (empty($userdata['ip']) || $userdata['ip'] !== $ip){
            $this->database->changeData('users', 'ip', $ip, $userdata['id']);
        }
    }

    public function checkUserDemoSubscription($userdata){
        $output = array('status' => false, 'description' => null);
        $userAgent = $this->formatter->getUserAgent();
        $existAgentData = $this->database->getDataByValue('users', 'agent', $userAgent);

        if (isset($existAgentData)){
            if ($userdata['id'] == $existAgentData['id']){
                $status = $this->checkSubscription($userdata['id']);
                if ($status){
                    $dates = $this->formatter->getSubscriptionsDates();
                    $this->database->addData('subscriptions', ['type' => 'demo', 'user' => $userdata['id'], 'dates' => $dates]);

                    $log = "Получена пробная подписка на {$this->configs['main']['demo']} ч.";
                    $this->database->addData('logs', ['user' => $userdata['id'], 'username' => $userdata['name'], 'usertype' => 'user', 'action' => $log]);

                    $output['status'] = $status;
                    $output['description'] = 'success';
                }
                else {
                    $output['description'] = 'already-used';
                }
            }
            else {
                $this->database->changeData('users', 'ban', true, $existAgentData['id']);
                $this->database->changeData('users', 'cause', 'abuse-demo', $existAgentData['id']);

                $log = "Пользователь попытался получить пробную подписку не на себя, а на пользователя [{$userdata['name']}](tg://user?id={$userdata['id']}).
                Данное действие расценено как попытка заабьюзить подписку, пользователь был автоматически забанен.";
                $this->database->addData('logs', ['user' => $userdata['id'], 'username' => $userdata['name'], 'usertype' => 'user', 'action' => $log]);

                $output['description'] = 'another-user';
            }

        }
        else {
            if (empty($userdata['agent'])) {
                $dates = $this->formatter->getSubscriptionsDates();
                $this->database->changeData('users', 'agent', $userAgent, $userdata['id']);
                $this->database->addData('subscriptions', ['type' => 'demo', 'user' => $userdata['id'], 'dates' => $dates]);

                $log = "Пользователю установлен юзер-агент «{$userAgent}» и выдана пробная подписка на {$this->configs['main']['demo']} ч.";
                $this->database->addData('logs', ['user' => $userdata['id'], 'username' => $userdata['name'], 'usertype' => 'user', 'action' => $log]);

                $output['status'] = true;
                $output['description'] = 'success';
            }
            else {
                if ($userdata['agent'] == $userAgent){
                    $status = $this->checkSubscription($userdata['id']);

                    if ($status){
                        $dates = $this->formatter->getSubscriptionsDates();
                        $this->database->addData('subscriptions', ['type' => 'demo', 'user' => $userdata['id'], 'dates' => $dates]);

                        $log = "Получена пробная подписка на {$this->configs['main']['demo']} ч.";
                        $this->database->addData('logs', ['user' => $userdata['id'], 'username' => $userdata['name'], 'usertype' => 'user', 'action' => $log]);

                        $output['status'] = $status;
                        $output['description'] = 'success';
                    }
                    else {
                        $output['description'] = 'already-used';
                    }
                }
                else {
                    $output['description'] = 'another-agent';
                }
            }
        }

        return $output;
    }

    public function checkSubscription($user){
        $status = true;
        $subscriptions = $this->database->getDataByValue('subscriptions', 'user', $user, null, null, 'array');

        if (count($subscriptions) > 0){
            foreach ($subscriptions as $subscription){
                if ($subscription[0] == 'demo'){
                    $status = false;
                    break;
                }
            }
        }

        return $status;
    }

}

class Formatter {
    public function __construct($configs){
        $this->configs = $configs;
    }

    public function getSubscriptionsDates(){
        $now= date('Y-m-d H:i:s');
        $expiration = date('Y-m-d H:i:s', strtotime("+{$this->configs['main']['demo']} hours"));
        return ['now' => $now, 'expiration' => $expiration];
    }


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
$formatter = new Formatter($configs);
$handler = new Handler($configs, $database, $formatter);
?>
