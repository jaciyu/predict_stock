# 导入所需的库
import pandas as pd
import numpy as np
import talib as tl
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

# 股票策略模版
# 初始化函数,全局只运行一次
def init(context):
    set_benchmark('000300.SH')
    log.info('策略开始运行,初始化函数全局只运行一次')
    set_commission(PerShare(type='stock',cost=0.0002))
    set_slippage(PriceSlippage(0.005))
    set_volume_limit(0.25,0.5)
    # 设置策略常量
    set_params(context)
    context.n = 30
    context.SECURITT_SIZE = -1
    context.TRADE_STOCK_SIZE = 100
    run_monthly(update_trade_stocks,date_rule=1)
    # 筛选出2005年上市且2019年尚未退市的股票池
    context.securities = get_securities()[:context.SECURITT_SIZE]
    # 使用沪深300作为股票池
    #context.securities = get_index_stocks('000300.SH')[:context.SECURITT_SIZE]
    # 获取08-16年季度财务数据
    #context.final_states = get_all_financial_statments(context.securities)
    # 获取的因子名称
    context.factor_info = ['growth_stat_ncf_of_oa_yoy', 'asharevalue_stat_pe_ttm', 'income_sq_stat_basic_eps', 
    'profit_sq_stat_roe_one_season', 'balance_stat_accrued_wages', 'ashareoperate_stat_account_receive_turnover_ttm']
    # (从文件获取08-16年季度财务数据
    print("====== 获取季度财务数据中 ======")
    context.final_states = {}
    count = 0
    for stock in context.securities:
        count = count + 1
        context.final_states[stock] = pd.read_csv('fundamental_data/%s'%stock)
        if count%200 == 0:
            print('(%d/%d)'%(count, len(context.securities)), end='\t')
    context.model = LSTM(model_dir='single_model', name_scope='rnn', input_size=19, time_steps=4, epoches=10)
    context.scalers = {}
    count = 0
    '''模型已经训练完成
    print("====== 模型训练中 ======")
    for stock in context.securities:
        count = count + 1
        # 数据标准化，均值=0，方差=1
        scaler = MinMaxScaler()
        context.final_states[stock] = scaler.fit_transform(context.final_states[stock])
        context.scalers[stock] = scaler
        # 模型训练
        if context.final_states[stock].shape[1] == len(context.factor_info):
            context.model.train(dataset=context.final_states[stock])
        if count%10 == 0:
            print('(%d/%d)'%(count,len(context.securities)))
    '''

## 开盘时运行函数, 用WR、RSI、OBV、PVT、BBI、VOSC技术指标进行量化择时
def handle_bar(context, bar_dict):
    empty_account = False   # 记录是否清仓
    
    # 获取账户持仓信息
    holdstock = list(context.portfolio.stock_account.positions.keys())
    if len(holdstock) > 0:
        num = -2
        # 获取富时中国A50指数，若今日跌幅大于2%，则清仓
        A50 = history('XIN9.FS',['quote_rate'],1,'1d').values
        if A50 <= num:
            print('富时中国A50指数下跌%.2f%%, 已清仓。'%(-A50))
            for stock in holdstock:
                order_target(stock,0)
            empty_account = True
        
    # 获取账户持仓信息
    holdstock = list(context.portfolio.stock_account.positions.keys())
    if len(holdstock) > 0:
        num = - 0.13
        T = history('000001.SH',['quote_rate'],7,'1d').values.sum()
        if T < num*100:
            print('上证指数7天内累计下跌%.2f%%, 已清仓。'%(-T))
            for stock in holdstock:
                order_target(stock,0)
            empty_account = True
    
    # 若未根据大盘清仓，则进行择时买卖
    if not empty_account:                
        # 根据择时返回的买卖股票列表操作
        will_buy, will_sell = timing(context, bar_dict)
        holdstock = list(context.portfolio.stock_account.positions.keys())
        for stock in holdstock:
            if stock in will_sell:
                order_target(stock, 0)
        for stock in will_buy:
            holdstock = list(context.portfolio.stock_account.positions.keys())
            if len(holdstock) < context.n and stock not in holdstock:
                number = context.n - len(holdstock)
                order_value(stock,context.portfolio.stock_account.available_cash/number)
        
def update_trade_stocks(context, bar_dict):
    current_date = get_datetime()
    print('===== update_trade_stocks:',current_date.strftime('%Y%m'), ' =====')
    # 如果当前持仓数为0, 应重新因子打分法选出新的股票池
    if len(list(context.portfolio.stock_account.positions.keys())) == 0:
        year = current_date.strftime('%Y')
        month = current_date.strftime('%m')
        year = int(year)
        month = int(month)
        fundamental_dates = []
        if month>=1 and month<=3:
            for season in ['q1','q2','q3','q4']:
                date = "%d%s" % (year-1, season)
                fundamental_dates.append(date)
        elif month>=4 and month<=6:
            for season in ['q2','q3','q4']:
                date = "%d%s" % (year-1, season)
                fundamental_dates.append(date)
            fundamental_dates.append("%dq1"%(year))
        elif month>=7 and month<=9:
            for season1 in ['q3','q4']:
                date = "%d%s" % (year-1, season1)
                fundamental_dates.append(date)
            for season2 in ['q1','q2']:
                date = "%d%s" % (year, season2)
                fundamental_dates.append(date)
        elif month>=10 and month<=12:
            fundamental_dates.append("%dq4"%(year-1))
            for season in ['q1','q2','q3']:
                date = "%d%s" % (year, season)
                fundamental_dates.append(date)
    else:
        fundamental_dates = get_fundamentals_dates(current_date)

    if fundamental_dates:
    # 如果到了下一季度初,应重新因子打分法选出新的股票池
        df_fundamental = pd.DataFrame(columns=context.factor_info)
        #count = 0
        factor_info = list(pd.read_csv('fundamental_data/000833.SZ').drop('statDate', axis=1).columns)
        for stock in context.securities:
            # df存储前4季度的财务因子数据
            df = pd.DataFrame()
            q = get_fundamental_q(stock)
            for date in fundamental_dates:
                #fundamental = get_fundamentals(query_object=q,statDate=date)
                fundamental = context.final_states[stock]
                # 沪深300模型 shape = (?,4,6)
                #fundamental = fundamental[fundamental['statDate']==date].drop(['statDate'],axis=1)[context.factor_info]
                fundamental = fundamental[fundamental['statDate']==date].drop(['statDate'],axis=1)
                if not fundamental.empty:
                    df = df.append(fundamental)
                else:
                    nan = np.zeros((1,))
                    nan[nan == 0] = np.nan
                    df = df.append(pd.DataFrame(nan))
            df = handle_stock_df(df)
            # 用对应的股票模型进行预测
            stock_prediction = context.model.predict(df.values)
            # 返回未经inverse_transform的prediction
            df_prediction = pd.DataFrame(stock_prediction, columns=factor_info)[context.factor_info]
            df_prediction.insert(0, 'stock', stock)
            df_fundamental = df_fundamental.append(df_prediction)
            #count = count + 1
            #if count%200 == 0:
                #print('(%d/%d)'%(count, len(context.securities)))
        df_fundamental = df_fundamental.reset_index(drop=True)
        # 使用因子打分法对股票进行排序，返回前300支股票作为trade_stock
        context.trade_stocks = score_factors(df_fundamental, context.TRADE_STOCK_SIZE)

## ===================== 以下为功能函数 =======================
# 设置策略参数
def set_params(context):
    context.SMA_s = 4                        # 设置SMA短期均线日期
    context.SMA_l = 40                       # 设置SMA长期均线日期
    context.fastperiod = 12                  # 设置MACD的fastperiod
    context.slowperiod = 26                  # 设置MACD的slowperiod
    context.signalperiod = 9                 # 设置MACD的signalperiod
    context.DMA_S = 4                        # 设置DMA的短期均线日期S
    context.DMA_L = 40                       # 设置DMA的长期均线日期L
    context.DMA_M = 20                       # 设置DMA的均线差值
    context.TRIX_N = 20                      # 设置TRIX的N值
    context.TRIX_M = 60                      # 设置TRIX的M值
# 计算SMA信号
def SMA_signal(context,bar_dict,stock):
    value = history(stock,['close'],200,'1d',True,'pre')
    value = value.dropna()
    close = value.close.values
    # 计算移动均线值
    sma = tl.SMA(close,context.SMA_s)
    lma = tl.SMA(close,context.SMA_l)
    # 判断信号
    if sma[-1]>sma[-2] and sma[-1]>lma[-1] and sma[-2]<lma[-2]:
        return 1
    elif sma[-1]<sma[-2] and sma[-1]<lma[-1] and sma[-2]>lma[-2]:
        return -1
    else:
        return 0
# 计算MACD信号
def MACD_signal(context,bar_dict,stock):
    value = history(stock,['close'],200,'1d',True,'pre')
    value = value.dropna()
    close = value.close.values
    # 计算macd值
    macd, dif, dea = tl.MACD(close,context.fastperiod,context.slowperiod,context.signalperiod)
    # 判断信号
    if dif[-1]>dif[-2] and dif[-1]>dea[-1] and dif[-2]<dea[-2] and dif[-1]>0:
        return 1
    elif dif[-1]<dif[-2] and dif[-1]<dea[-1] and dif[-2]>dea[-2] and dif[-1]<0:
        return -1
    else:
        return 0
# 计算DMA信号
def DMA_signal(context,bar_dict,stock):
    value = history(stock,['close'],200,'1d',True,'pre')
    value = value.dropna()
    close = value.close.values
    # 计算移动均线值和差值
    sma = tl.SMA(close,context.DMA_S)
    lma = tl.SMA(close,context.DMA_L)
    # 计算DMA
    DMA = sma-lma
    AMA = tl.SMA(DMA,context.DMA_M)
    # 判断信号
    if DMA[-1]>DMA[-2] and DMA[-1]>AMA[-1] and DMA[-2]<AMA[-2]:
        return 1
    elif DMA[-1]<DMA[-2] and DMA[-1]<AMA[-1] and DMA[-2]>AMA[-2]:
        return -1
    else:
        return 0
# 计算TRIX信号
def TRIX_signal(context,bar_dict,stock):
    value = history(stock,['close'],300,'1d',True,'pre')
    value = value.dropna()
    close = value.close.values
    # 计算TR
    EMA1 = tl.SMA(close,context.TRIX_N)
    EMA2 = tl.SMA(EMA1,context.TRIX_N)
    TR = tl.SMA(EMA2,context.TRIX_N)
    # 计算TRIX 和 MATTRIX
    value['TR'] = TR
    value['TRIX'] = value.TR/value.TR.shift(1)-1.0
    TRIX = value.TRIX.values
    MATTRIX = tl.SMA(TRIX,context.TRIX_M)
    # 判断信号
    if TRIX[-1]>TRIX[-2] and TRIX[-1]>MATTRIX[-1] and TRIX[-2]<MATTRIX[-2]:
        return 1
    elif TRIX[-1]<TRIX[-2] and TRIX[-1]<MATTRIX[-1] and TRIX[-2]>MATTRIX[-2]:
        return -1
    else:
        return 0
# 计算交易信号
def stock_to_signals(context,bar_dict,stock):
    signal_1 = SMA_signal(context,bar_dict,stock)                   #计算SMA信号
    signal_2 = MACD_signal(context,bar_dict,stock)                  #计算MACD信号
    signal_3 = DMA_signal(context,bar_dict,stock)                   #计算DMA信号
    signal_4 = TRIX_signal(context,bar_dict,stock)                  #计算TRIX信号
    #返回信号值
    return signal_1+signal_2+signal_3+signal_4
# 排序交易信号，返回买卖股票表
def timing(context,bar_dict):
    # 计算交易信号
    df_signal = pd.DataFrame(columns=['stock', 'signal'])
    i = 0
    for stock in context.trade_stocks:
        df_signal.loc[i, 'stock'] = stock
        signal = stock_to_signals(context,bar_dict,stock)  
        df_signal.loc[i, 'signal'] = signal
        i = i + 1
    will_buy = list(df_signal[df_signal['signal']>=1].sort_values(by='signal', ascending=False)['stock'])
    will_sell = list(df_signal[df_signal['signal']<=-1].sort_values(by='signal')['stock'])
    return will_buy, will_sell

# 筛选出2005年上市且2019年尚未退市的股票池，用于获取训练数据
def get_securities():
    # 获取A股所有股票
    univers = list(get_all_securities('stock').index)
    # 筛选出2005年以前上市且尚未退市的股票
    securities = []
    for stock in univers:
        info = get_security_info(stock)
        if info.start_date.strftime("%Y") <= '2005' and info.end_date.strftime("%Y") == '2200':
            securities.append(stock)
    # 剔除股票池中ST>=0.3的股票
    stock_list = []
    for stock in securities:
        st_days = np.sum(get_price(securities=stock, start_date='20060101', end_date='20141230', fields=['is_st']))['is_st']
        if st_days < 9*250*0.3:
            stock_list.append(stock)
    securities = stock_list
    return securities

def get_fundamental_q(stock):
    q = query(
            asharevalue.pe_ttm,#市盈率
            #asharevalue.pb_mrq,#市净率
            #asharevalue.ps_ttm,#市销率
            profit_sq.roe_one_season,#净资产收益率roe（单季度）
            income_sq.basic_eps,#基本每股收益
            #asharevalue.total_mv,#总市值
            #ashareprofit.net_sales_rate_ttm,#销售净利率
            #asharedebt.equity_ratio_mrq,#产权比率
            #balance.fixed_asset,#固定资产
            #growth.net_asset_growth_ratio,#净资产(同比增长率)
            #profit_report.asset,#总资产
            #factor.opt_income_growth_ratio,#营业收入同比增长率
            ashareoperate.account_receive_turnover_ttm,#应收账款周转率
            #ashareoperate.accounts_payable_turnover_ttm,#应付账款周转率
            #ashareoperate.total_capital_turnover_ttm,#总资产周转率
            growth.ncf_of_oa_yoy,#经营活动产生的现金流量净额(同比增长率)
            #income_sq.overall_income,#营业总收入
            #income_sq.overall_costs,#营业总成本
            #income_sq.net_profit,#净利润
            #cashflow_sq.net_increase_in_cce,#现金及现金等价物净增加额
            #balance.long_term_receivables,#长期应收款
            #balance.receivable_other,#其他应收款
            #balance.total_non_current_assets,#非流动资产合计
            balance.accrued_wages,#应付职工薪酬
            #balance.current_liabilities#流动负债合计
        ).filter(
            income_sq.symbol == stock)
    return q

def handle_stock_df(df):
    # 某行全为nan,则删除该行
    #df = df.dropna(how='all')
    # 某列缺失数据大于15%，则删除该列
    #for column in list(df.columns[df.isnull().sum() > (len(df)*0.15)]):
    #    df.drop(column, axis=1, inplace=True)
    # 缺失值用均值填充
    for column in list(df.columns[df.isnull().sum()>0]):
        mean_val = df[column].mean()
        df[column].fillna(mean_val, inplace=True)
    df = df.fillna(0)
    try:
        df = df.drop([0],axis=1)
    except:
        pass
    return df

# 获取08-16年，共36个季度的数据
def get_all_financial_statments(securities):
    years = [8,9,10,11,12,13,14,15,16,17,18]
    seasons = [1,2,3,4]
    stock_df_all = {}
    count = 0 # 用于计数
    for stock in securities:
        count = count + 1
        if count%10 == 0:
            print(stock+'(%d/%d)'%(count, len(securities)), end='\t')
        df = pd.DataFrame()
        q = get_fundamental_q(stock)
        for year in years:
            for season in seasons:
                date = '20%(year)02dq%(season)d'%{'year':year, 'season':season}
                fundamental = get_fundamentals(query_object=q, statDate=date)
                if fundamental.empty:
                    nan = np.zeros((1))
                    nan[nan == 0] = np.nan
                    df = df.append(pd.DataFrame(nan))
                else:
                    df = df.append(fundamental)
        df = handle_stock_df(df)
        df = df.reset_index(drop=True)
        stock_df_all[stock] = df
    return stock_df_all
  
# 判断当前日期是否为获取季度财务报表的日期
def get_fundamentals_dates(date):
    year = date.strftime('%Y')
    month = date.strftime('%m')
    year = int(year)
    month = int(month)
    fundamental_dates = []
    if month == 1:
        for season in ['q1','q2','q3','q4']:
            date = "%d%s" % (year-1, season)
            fundamental_dates.append(date)
    elif month == 4:
        for season in ['q2','q3','q4']:
            date = "%d%s" % (year-1, season)
            fundamental_dates.append(date)
        fundamental_dates.append("%dq1"%(year))
    elif month == 7:
        for season1 in ['q3','q4']:
            date = "%d%s" % (year-1, season1)
            fundamental_dates.append(date)
        for season2 in ['q1','q2']:
            date = "%d%s" % (year, season2)
            fundamental_dates.append(date)
    elif month == 10:
        fundamental_dates.append("%dq4"%(year-1))
        for season in ['q1','q2','q3']:
            date = "%d%s" % (year, season)
            fundamental_dates.append(date)
    return fundamental_dates

# 因子打分法选出股票池
def score_factors(df_fundamental, size):
    # 打分环节
    df_fundamental['score'] = 0
    for i in range(len(df_fundamental)):
        df = df_fundamental.iloc[i]
        score = df['growth_stat_ncf_of_oa_yoy'] + df['asharevalue_stat_pe_ttm'] + df['income_sq_stat_basic_eps'] \
        - df['profit_sq_stat_roe_one_season'] - df['balance_stat_accrued_wages'] - df['ashareoperate_stat_account_receive_turnover_ttm']
        df_fundamental.loc[i, 'score'] = score
    # 按score降序排序
    df_fundamental = df_fundamental.sort_values(by='score', ascending=False)
    trade_stocks = list(df_fundamental['stock'][:size])
    return trade_stocks


## ========== 以下为LSTM模型 ==========
class LSTM():
    def __init__(self, model_dir, name_scope, input_size, time_steps, batch_size=16, hidden_units = 128, learning_rate=0.01, epoches=100):
        self.name_scope = name_scope
        self.model_dir = model_dir
        self.input_size = input_size
        self.time_steps = time_steps
        self.hidden_units = hidden_units
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.epoches = epoches
        self.NetInit()
    
    def weight_variable(self, shape):
        with tf.name_scope('weights'):
            return tf.Variable(tf.truncated_normal(shape, stddev=0.1), name='W')
    
    def bias_variable(self, shape):
        with tf.name_scope('biases'):
            return tf.Variable(tf.constant(0.1, shape=shape))

    def NetInit(self):
        with tf.name_scope('Inputs'):
            self.x = tf.placeholder(tf.float32, [None, self.time_steps, self.input_size], name='x_input')
            self.y_ = tf.placeholder(tf.float32, [None, self.input_size], name='y_input')

        weights = {
            'in': self.weight_variable([self.input_size, self.hidden_units]),
            'out': self.weight_variable([self.hidden_units, self.input_size])
        }
        biases = {
            'in': self.bias_variable([self.hidden_units, ]),
            'out': self.bias_variable([self.input_size, ])
        }
        
        # RNN
        x = tf.reshape(self.x, [-1, self.input_size])
        with tf.name_scope('Wx_plus_b'):
            x_in = tf.matmul(x, weights['in']) + biases['in']
        x_in = tf.reshape(x_in, [-1, self.time_steps, self.hidden_units])

        
        # basic LSTM Cell.
        cell = tf.contrib.rnn.BasicLSTMCell(self.hidden_units, forget_bias=1.0)
        # lstm cell is divided into two parts (c_state, h_state)
        init_state = cell.zero_state(self.batch_size, dtype=tf.float32)

        outputs, final_state = tf.nn.dynamic_rnn(cell, x_in, initial_state=init_state, time_major=False, scope=self.name_scope)

        self.prediction = tf.matmul(final_state[1], weights['out']) + biases['out']    # shape = (batch_size, input_size)

        with tf.name_scope('loss'):
            self.loss = tf.losses.mean_squared_error(labels=self.y_, predictions=self.prediction)
        with tf.name_scope('train'):
            self.train_op = tf.train.AdamOptimizer(self.learning_rate).minimize(self.loss)

        config = tf.ConfigProto(allow_soft_placement=True, log_device_placement=True)  
        config.gpu_options.allow_growth = True  
        self.sess = tf.Session(config=config) 

        self.sess.run(tf.local_variables_initializer())
        self.sess.run(tf.global_variables_initializer())

        self.saver=tf.train.Saver(max_to_keep=1)
        self.saver.restore(self.sess, tf.train.latest_checkpoint(self.model_dir))

    def handle_predict_data(self, predict_data):
        predict_data = predict_data[np.newaxis, :]
        return_data = predict_data
        for i in range(self.batch_size-1):
            return_data = np.vstack([return_data, predict_data])
        return return_data  # (batch_size, time_steps, input_size)

    def get_batches(self, dataset):
        length = dataset.shape[0]
        x_batches = []
        y_batches = []
        for i in range(length-self.batch_size-self.time_steps-1):
            batch = []
            batch_label = []
            for j in range(self.batch_size):
                batch.append(dataset[i+j:i+j+self.time_steps])
                batch_label.append(dataset[i+j+self.time_steps])
            x_batches.append(batch)
            y_batches.append(batch_label)
        x_batches = np.array(x_batches)
        y_batches = np.array(y_batches)
        return x_batches, y_batches

    def train(self, dataset):
        min_loss = 1
        for i in range(self.epoches+1):
            x_batches, y_batches = self.get_batches(dataset)
            assert len(x_batches) == len(y_batches)
            for j in range(len(x_batches)):
                train_data = x_batches[j]
                train_label = y_batches[j]
                self.sess.run (self.train_op, feed_dict = {self.x: train_data, self.y_: train_label})
            train_loss = self.get_loss(x_batches[0], y_batches[0])
            if train_loss < min_loss:
                min_loss = train_loss
                self.saver.save(self.sess, '%s/%s.ckpt'%(self.model_dir, self.model_dir))

    def get_loss(self, data, label):
        return self.sess.run(self.loss, feed_dict={self.x: data, self.y_: label})
    
    def predict(self, data):
        data = self.handle_predict_data(data)
        return self.sess.run(self.prediction, feed_dict={self.x: data})[-1].reshape(1, -1)

# 性能分析
enable_profile()