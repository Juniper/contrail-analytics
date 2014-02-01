/*
 * Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
 */
#include <iostream>
#include <cstdlib>
#include <string>
#include <map>
#include <boost/array.hpp>
#include <boost/bind.hpp>
#include <boost/shared_ptr.hpp>
#include <boost/asio.hpp>
#include "base/misc_utils.h"
#include <boost/spirit/include/qi.hpp>
//#include <boost/phoenix/bind/bind_function_object.hpp>
#include <boost/spirit/include/phoenix.hpp>
#include <boost/spirit/include/phoenix_core.hpp>
#include <boost/spirit/include/phoenix_operator.hpp>
#include <boost/spirit/include/phoenix_stl.hpp>
#include <boost/spirit/home/phoenix/object/construct.hpp>
#include <boost/uuid/uuid.hpp>
#include <boost/uuid/uuid_generators.hpp>
#include <boost/uuid/uuid_io.hpp>
#include <boost/assign/list_of.hpp>

#include <boost/fusion/adapted/std_pair.hpp>
#include "syslog_collector.h"
#include "base/logging.h"
#include "generator.h"
#include <sandesh/sandesh_types.h>
#include <sandesh/sandesh.h>
#include <base/util.h>

/*** test for burst (compile <string> with  -lboost_date_time -lboost_thread and
 * no -fno-exceptions
#include <boost/date_time/posix_time/posix_time.hpp>
#include <boost/thread/thread.hpp>
**/

using boost::asio::ip::udp;
using namespace boost::asio;
namespace qi = boost::spirit::qi;
namespace ascii = boost::spirit::ascii;
namespace bt = boost::posix_time;
namespace phx = boost::phoenix;


class SyslogQueueEntry;

class SyslogTcpSession : public TcpSession
{
  public:
    typedef boost::intrusive_ptr<SyslogTcpSession> SyslogTcpSessionPtr;

    SyslogTcpSession (SyslogTcpListener *server, Socket *socket);
    virtual void OnRead (boost::asio::const_buffer buf);
    void Parse (SyslogQueueEntry &sqe);
  private:
    SyslogTcpListener *listner_;
};


class TCPSyslogQueueEntry : public SyslogQueueEntry
{
    private:
        typedef boost::intrusive_ptr<SyslogTcpSession> SyslogTcpSessionPtr;
    public:
    TCPSyslogQueueEntry (SyslogTcpSessionPtr ses, boost::asio::const_buffer b,
            ip::tcp::endpoint e) :
      buf_ (b), ep_ (e), session_(ses)  {
        data = buffer_cast<const uint8_t *>(b);
        length = buffer_size (b);
        ip = e.address ().to_string ();
        port = e.port ();
    }
    virtual void free ();
    private:
    boost::asio::const_buffer   buf_;
    ip::tcp::endpoint           ep_;
    SyslogTcpSessionPtr         session_;
};

class SyslogUDPListener;
class UDPSyslogQueueEntry : public SyslogQueueEntry
{
    public:

    UDPSyslogQueueEntry (SyslogUDPListener* svr, udp::endpoint *ep,
            mutable_buffer *d, size_t l):
        ep_ (ep), mb_ (d), server_ (svr) {
        data = buffer_cast<uint8_t *>(*d);
        length = l;
        ip = ep->address ().to_string ();
        port = ep->port ();
    }
    virtual void free ();
    private:
    udp::endpoint          *ep_;
    mutable_buffer         *mb_;
    SyslogUDPListener      *server_;
};


class SyslogParser
{
    // http://www.ietf.org/rfc/rfc3164.txt
    public:
        SyslogParser (SyslogListeners *syslog):
             work_queue_(TaskScheduler::GetInstance()->GetTaskId(
                         "vizd::syslog"), 0, boost::bind(
                             &SyslogParser::ClientParse, this, _1)),
            syslog_(syslog)
        {
            facilitynames_ = boost::assign::list_of ("auth") ("authpriv")
                ("cron") ("daemon") ("ftp") ("kern") ("lpr") ("mail") ("mark")
                ("news") ("security") ("syslog") ("user") ("uucp") ("local0")
                ("local1") ("local2") ("local3") ("local4") ("local5")
                ("local6") ("local7");
        }
        SyslogParser (const SyslogParser &sp):
             work_queue_(TaskScheduler::GetInstance()->GetTaskId(
                         "vizd::syslog"), 0, boost::bind(
                             &SyslogParser::ClientParse, this, _1)) {
        }
        void Parse (SyslogQueueEntry &sqe) {
            work_queue_.Enqueue (sqe);
        }

        void Shutdown ()
        {
            WaitForIdle (15); // wait for 15 sec..
            work_queue_.Shutdown ();
            LOG(DEBUG, __func__ << " Syslog parser shutdown done");
        }
    private:

        void WaitForIdle (int max_wait)
        {
            int i;
            TaskScheduler *scheduler = TaskScheduler::GetInstance();
            for (i = 0; !scheduler->IsEmpty() && i < max_wait; i++) {
                usleep (1000);
                LOG(DEBUG, __func__ << " Syslog queue empty? " <<
                        scheduler->IsEmpty() << ":" << i << "/" << max_wait);
            }
            LOG(DEBUG, __func__ << " Syslog queue empty? " <<
                    scheduler->IsEmpty() << ":" << i << "/" << max_wait);
        }

        enum dtype {
            int_type = 42,
            str_type
        };
        struct Holder {
            std::string       key;
            dtype             type;
            int64_t           i_val;
            std::string       s_val;

            Holder (std::string k, std::string v):
                key(k), type(str_type), s_val(v)
            { }
            Holder (std::string k, int64_t v):
                key(k), type(int_type), i_val(v)
            { }

            void print ()
            {
                std::cout << "{ \"" << key << "\": ";
                if (type == int_type)
                    std::cout << i_val << "}";
                else if (type == str_type)
                    std::cout << "\"" << s_val << "\"}";
                else
                    std::cout << "**bad type**}";
            }
        };

        typedef std::map<std::string, Holder>  syslog_m_t;

        struct months_: qi::symbols<char, int>
        {
            months_()
            {
                add
                    ("Jan", 1)
                    ("Feb", 2)
                    ("Mar", 3)
                    ("Apr", 4)
                    ("May", 5)
                    ("Jun", 6)
                    ("Jul", 7)
                    ("Aug", 8)
                    ("Sep", 9)
                    ("Oct", 10)
                    ("Nov", 11)
                    ("Dec", 12)
                ;
            }
        } months;

        template <typename Iterator>
        bool parse_syslog (Iterator start, Iterator end, syslog_m_t &v)
        {
            using qi::int_;
            using qi::_1;
            using ascii::space;
            using phx::insert;
            using qi::eps;
            using qi::char_;
            using qi::lit;
            using qi::lexeme;

            qi::rule<Iterator, std::string(), ascii::space_type> word = lexeme[ +(char_ - ' ') ] ;
            qi::rule<Iterator, std::string(), ascii::space_type> word2 = lexeme[ +(char_ - ':' - ' ') ] ;
            qi::rule<Iterator, std::string(), ascii::space_type> word3 = lexeme[ +(char_ - '[' - ' ' - ':') ] ;
            qi::rule<Iterator, std::string(), ascii::space_type> body = lexeme[ *char_ ] ;
            qi::int_parser<int, 10, 1, 3> int3_p;
            qi::int_parser<int, 10, 1, 2> int2_p;
            qi::int_parser<int, 10, 1, 1> int1_p;

            bool r = qi::phrase_parse(start, end,
                    // Begin grammer
                                       //facility severity
                    (  '<' >> int_     [insert(phx::ref(v),
                phx::construct<std::pair<std::string, Holder> >("facsev",
                          phx::construct<Holder>("facsev", _1)))] >> '>'
                                       //month
                       >> months       [insert(phx::ref(v),
                phx::construct<std::pair<std::string, Holder> >("month",
                                  phx::construct<Holder>("month", _1)))]
                                       //day
                       >> int_         [insert(phx::ref(v),
                phx::construct<std::pair<std::string, Holder> >("day",
                                  phx::construct<Holder>("day", _1)))]
                                       //hour
                       >> int_         [insert(phx::ref(v),
                phx::construct<std::pair<std::string, Holder> >("hour",
                          phx::construct<Holder>("hour", _1)))] >> lit(":")
                                       //min
                       >> int_         [insert(phx::ref(v),
                phx::construct<std::pair<std::string, Holder> >("min",
                          phx::construct<Holder>("min", _1)))] >> lit(":")
                                       //sec
                       >> int_         [insert(phx::ref(v),
                phx::construct<std::pair<std::string, Holder> >("sec",
                                  phx::construct<Holder>("sec", _1)))]
                                       //hostname
                       >> word         [insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("hostname",
                                  phx::construct<Holder>("hostname", _1)))]
                                       //tag body
                                       //  tag=prog[pid]:
                       >> ( ( word3    [insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("prog",
                          phx::construct<Holder>("prog", _1)))] >> lit("[")
                              >> int_  [insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("pid",
                          phx::construct<Holder>("pid", _1)))] >> lit("]:")
                                       //  tag=prog:
                              |word2   [insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("prog",
                              phx::construct<Holder>("prog", _1))),
                                        insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("pid",
                          phx::construct<Holder>("pid", -1)))] >> lit(":")
                                       //  body
                            ) >>body   [insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("body",
                                      phx::construct<Holder>("body", _1)))]
                                       //body w/ no tag
                            |body      [insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("prog",
                                  phx::construct<Holder>("prog", ""))),
                                        insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("pid",
                                  phx::construct<Holder>("pid", -1))),
                                        insert(phx::ref(v),
            phx::construct<std::pair<std::string, Holder> >("body",
                                  phx::construct<Holder>("body", _1)))]
                          )
                    )
                    //end grammer
                    , space);
            return (start == end) && r;
        }

        std::string GetMapVals (syslog_m_t v, std::string key,
                std::string def = "")
        {
            std::map<std::string, Holder>::iterator i = v.find (key);
            if (i == v.end())
                return def;
            return i->second.s_val;
        }

        int64_t GetMapVal (syslog_m_t v, std::string key, int def = 0)
        {
            std::map<std::string, Holder>::iterator i = v.find (key);
            if (i == v.end())
                return def;
            return i->second.i_val;
        }

        void GetFacilitySeverity (syslog_m_t v, int& facility, int& severity)
        {
            int fs = GetMapVal (v, "facsev");
            severity = fs & 0x7;
            facility = fs >> 3;
        }

        void GetTimestamp (syslog_m_t v, time_t& timestamp)
        {
            bt::ptime lt(bt::microsec_clock::local_time());
            bt::ptime ut(bt::microsec_clock::universal_time());
            bt::time_duration diff = lt - ut;
            tm pt_tm = bt::to_tm(lt);
            bt::ptime p(boost::gregorian::date (pt_tm.tm_year+1900,
                GetMapVal (v, "month", pt_tm.tm_mon),
                GetMapVal (v, "day", pt_tm.tm_mday)), bt::time_duration(
                    GetMapVal (v, "hour", pt_tm.tm_hour),
                    GetMapVal (v, "min", pt_tm.tm_min),
                    GetMapVal (v, "sec", pt_tm.tm_sec)));
            bt::ptime epoch(boost::gregorian::date(1970,1,1));
            timestamp = (p - epoch).total_microseconds()
                            - diff.total_microseconds();
            /*
            time_t _timestamp = UTCTimestampUsec ();
            std::cout << "ts diff " << timestamp - _timestamp  << std::endl
                << timestamp << std::endl <<  _timestamp << std::endl;
            */
        }

        void PostParsing (syslog_m_t &v) {
          time_t timestamp;
          GetTimestamp (v, timestamp);
          v.insert(std::pair<std::string, Holder>("timestamp",
                Holder("timestamp", timestamp)));
          int f, s;
          GetFacilitySeverity (v, f, s);
          v.insert(std::pair<std::string, Holder>("facility",
                Holder("facility", f)));
          v.insert(std::pair<std::string, Holder>("severity",
                Holder("severity", s)));
        }

        SyslogGenerator GetGenerator (std::string ip)
        {
            std::map<std::string, SyslogGenerator>::iterator i =
                                                genarators_.find (ip);
            if (i == genarators_.end()) {

                genarators_.insert (std::pair<std::string, SyslogGenerator>(
                        ip, SyslogGenerator(syslog_, ip, "syslog")));
                i = genarators_.find (ip);
            }
            return i->second;
        }

        std::string GetSyslogFacilityName (uint64_t f)
        {
            if (f < facilitynames_.size ())
                return facilitynames_[f];
            return "";
        }

        std::string EscapeXmlTags (std::string text)
        {
            std::ostringstream s;

            for (std::string::const_iterator it = text.begin();
                                             it != text.end(); ++it) {
                switch(*it) {
                    case '&':  s << "&amp;";  continue;
                    case '"':  s << "&quot;"; continue;
                    case '\'': s << "&apos;"; continue;
                    case '<':  s << "&lt;";   continue;
                    case '>':  s << "&gt;";   continue;
                    default:   s << *it;
                }
            }
            return s.str();
        }

        std::string GetMsgBody (syslog_m_t v) {
            return EscapeXmlTags (GetMapVals (v, "body", ""));
        }

        void MakeSandesh (syslog_m_t v) {
            SandeshHeader hdr;
            std::string   ip(GetMapVals (v, "ip"));

            hdr.set_Timestamp(GetMapVal (v, "timestamp"));
            hdr.set_Module(GetMapVals (v, "prog", "UNKNOWN"));
            hdr.set_Source(GetMapVals (v, "hostname", GetMapVals (v, "ip")));
            hdr.set_Type(SandeshType::SYSLOG);
            hdr.set_Level (GetMapVal (v, "severity"));
            hdr.set_Category (GetSyslogFacilityName(GetMapVal(v, "facility")));
            hdr.set_IPAddress (ip);
            hdr.set_Pid (GetMapVal (v, "pid", -1));

            boost::shared_ptr<VizMsg> msg(new VizMsg(hdr, "SYSLOG",
                    "<Syslog>" + GetMsgBody (v) + "</Syslog>",
                    umn_gen_ ()));
            GetGenerator (ip).ReceiveSandeshMsg (msg, false);
        }

        bool ClientParse (SyslogQueueEntry sqe) {
          const uint8_t *p = sqe.data;
//#define SYSLOG_DEBUG 0
#ifdef SYSLOG_DEBUG
          std::cout << "cnt parser " << sqe.length << " bytes from (" <<
              sqe.ip << ":" << sqe.port << ")[";

          for (const uint8_t *q = p; q != p + sqe.length; q++)
              std::cout << *q;
          std::cout << "]\n";
#endif

          syslog_m_t v;
          bool r = parse_syslog (p, p + sqe.length, v);
#ifdef SYSLOG_DEBUG
          std::cout << "parsed " << r << "." << std::endl;
#endif

          v.insert(std::pair<std::string, Holder>("ip",
                Holder("ip", sqe.ip)));
          PostParsing (v);

          MakeSandesh (v);

          LOG(DEBUG, __func__ << " syslog msg from " << sqe.ip << ":" <<
                GetMapVals (v, "body", "**EMPTY**"));

#ifdef SYSLOG_DEBUG
          int i = 0;
          while (!v.empty()) {
              std::cout << i++ << ": ";
              Holder d = v.begin()->second;
              d.print ();
              std::cout << std::endl;
              v.erase(v.begin());
          }
#else
          v.erase(v.begin(), v.end());
#endif
          sqe.free ();
/*** test for burst
          boost::this_thread::sleep(boost::posix_time::milliseconds(20000UL));
**/
          return r;
        }
        WorkQueue<SyslogQueueEntry>               work_queue_;
        boost::uuids::random_generator            umn_gen_;
        std::map<std::string, SyslogGenerator>    genarators_;
        SyslogListeners                          *syslog_;
        std::vector<std::string>                  facilitynames_;
};

void SyslogQueueEntry::free ()
{
}

SyslogTcpListener::SyslogTcpListener (EventManager *evm):
          TcpServer(evm), session_(NULL)
{
}

TcpSession *SyslogTcpListener::AllocSession(Socket *socket)
{
    session_ = new SyslogTcpSession (this, socket);
    return session_;
}
void SyslogTcpListener::Shutdown ()
{
    // server shutdown
    TcpServer::Shutdown();
}
void SyslogTcpListener::Start (std::string ipaddress, int port)
{
    Initialize (port);
    LOG(DEBUG, __func__ << " Initialization of TCP syslog listener done!");
}

SyslogUDPListener::SyslogUDPListener (EventManager *evm): UDPServer (evm)
{
}
void SyslogUDPListener::Shutdown ()
{
    UDPServer::Shutdown ();
}
void SyslogUDPListener::Start (std::string ipaddress, int port)
{
    if (ipaddress.empty())
      Initialize (port);
    else
      Initialize (ipaddress, port);
    StartReceive ();
    LOG(DEBUG, __func__ << " Initialization of UDP syslog listener done!");
}

void SyslogUDPListener::HandleReceive (mutable_buffer *recv_buffer,
            udp::endpoint *remote_endpoint, std::size_t bytes_transferred,
            const boost::system::error_code& error)
{
    // TODO: handle error
    UDPSyslogQueueEntry sqe (this, remote_endpoint,
            recv_buffer, bytes_transferred);
    Parse (sqe);
    StartReceive();
}


SyslogListeners::SyslogListeners (EventManager *evm, Ruleeng *ruleeng,
            DbHandler *db_handler, std::string ipaddress, int port):
              SyslogUDPListener(evm), SyslogTcpListener(evm),
              parser_(new SyslogParser (this)), port_(port),
              ipaddress_(ipaddress), inited_(false),
              cb_(boost::bind(&Ruleeng::rule_execute, ruleeng, _1, _2, _3)),
              db_handler_ (db_handler)
{
}
SyslogListeners::SyslogListeners (EventManager *evm, Ruleeng *ruleeng,
        DbHandler *db_handler, int port):
          SyslogUDPListener(evm), SyslogTcpListener(evm),
          parser_(new SyslogParser (this)), port_(port), ipaddress_(),
          inited_(false),
          cb_(boost::bind(&Ruleeng::rule_execute, ruleeng, _1, _2, _3)),
          db_handler_ (db_handler)
{
}
void SyslogListeners::Start ()
{
    if (port_ != -1) {
        SyslogTcpListener::Start (ipaddress_, port_);
        SyslogUDPListener::Start (ipaddress_, port_);
        inited_ = true;
    }
}
void SyslogListeners::Parse (SyslogQueueEntry &sqe)
{
    //LOG(DEBUG, __func__ << " syslog Parsing msg");
    parser_->Parse (sqe);
}
bool SyslogListeners::IsRunning ()
{
    return inited_;
}
void SyslogListeners::Shutdown ()
{
    SyslogTcpListener::Shutdown ();
    SyslogUDPListener::Shutdown ();
    parser_->Shutdown ();
    inited_ = false;
}

void
TCPSyslogQueueEntry::free () {
    session_->ReleaseBuffer(buf_);
    session_->server()->DeleteSession (session_.get());
}
void
UDPSyslogQueueEntry::free () {
    server_->DeallocateBuffer (mb_);
    server_->DeallocateEndPoint (ep_);
}
SyslogTcpSession::SyslogTcpSession (SyslogTcpListener *server, Socket *socket) :
      TcpSession(server, socket), listner_ (server) {
          //set_observer(boost::bind(&SyslogTcpSession::OnEvent, this, _1, _2));
}
void
SyslogTcpSession::Parse (SyslogQueueEntry &sqe)
{
  listner_->Parse (sqe);
}
void
SyslogTcpSession::OnRead (boost::asio::const_buffer buf)
{
    boost::system::error_code ec;
    // TODO: handle error
    TCPSyslogQueueEntry    sqe(SyslogTcpSessionPtr (this), buf,
            socket ()->remote_endpoint(ec));
    Parse (sqe);
}


#if 0
int main()
{
    boost::system::error_code e;
    SyslogListeners          *s;
    std::auto_ptr<EventManager>    evm;
    std::auto_ptr<ServerThread>    thread;

    evm.reset(new EventManager());
    s = new SyslogListeners (evm.get());
    thread.reset(new ServerThread(evm.get()));
    thread->Start();
    s->Start ();

    // io_service.run()
    return 0;

}
#endif
//#undef  BOOST_NO_UNREACHABLE_RETURN_DETECTION
