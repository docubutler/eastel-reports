/*
Query 1: Active subscribers with MO traffic in the report window.

Output:
{
  service_type: "Active Subscriber",
  charge_type: "Total Active Subscriber Current",
  total: 9118
}
*/

db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      service_type_sub_cd: "MO",
      rat_type: { $in: ["VO", "SM", "4G", "5G"] },
      msisdn: { $exists: true, $ne: null }
    }
  },
  {
    $addFields: {
      msisdn_trimmed: {
        $trim: {
          input: { $toString: "$msisdn" }
        }
      }
    }
  },
  {
    $match: {
      msisdn_trimmed: { $ne: "" }
    }
  },
  {
    $group: {
      _id: "$msisdn_trimmed"
    }
  },
  {
    $group: {
      _id: null,
      total: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Active Subscriber" },
      charge_type: { $literal: "Total Active Subscriber Current" },
      total: 1
    }
  }
]);
