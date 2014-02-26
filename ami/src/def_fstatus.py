status = {
          'dram_bad'          :{'start_bit':6,  'width':1, 'default':False},
          'clk_bad'           :{'start_bit':5,  'width':1, 'default':False}, 
          'armed'             :{'start_bit':30, 'width':1, 'default':False},
          'adc_disable'       :{'start_bit':4,  'width':1, 'default':False},
          'sync_val'          :{'start_bit':10, 'width':2, 'default':0    },
          'quant_or'          :{'start_bit':0,  'width':1, 'default':False},
          'fft_or'            :{'start_bit':1,  'width':1, 'default':False},
          'adc_or'            :{'start_bit':2,  'width':1, 'default':False},
          'ct_error'          :{'start_bit':3,  'width':1, 'default':False},
          'xaui_of'           :{'start_bit':7,  'width':1, 'default':False},
          'xaui_down'         :{'start_bit':9,  'width':1, 'default':False},
          'phase_switch_on'   :{'start_bit':31, 'width':1, 'default':True },
          }
